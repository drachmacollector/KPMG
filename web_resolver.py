"""
web_resolver.py
---------------
Online Institution Resolution stage for the MAHABOCW Medical Scholarship
Verification pipeline.

Responsibility
--------------
Takes the noisy college name and address produced by the Qwen OCR extraction
stage and resolves them to the real, official institution name by performing a
Google Search and asking Gemini to rank the results.

The OCR-extracted address is treated as authoritative.  The web resolver is
used ONLY to canonicalise the institution name.

Architecture
------------
Three clean, replaceable layers:

  SearchProvider  (abstract)
    └─ SerpApiProvider    ← currently wired in
    └─ <future providers> ← Brave, Bing, Tavily, Vertex …

  LLMClient  (abstract)
    └─ GeminiClient       ← currently wired in
    └─ <future clients>   ← GPT, Claude, Ollama …

  resolve_institution()   ← single public entry point

Swapping the search engine or LLM requires only:
  1. Adding a new subclass.
  2. Changing the one-line wiring in resolve_institution().

Query Generation
----------------
  _build_queries() returns a priority-ordered list of query strings.
  Adding new strategies (abbreviation removal, stop-word stripping,
  trust-name removal, BHMS/BAMS removal, etc.) only requires appending
  to that list — resolve_institution() never needs to change.

Usage
-----
  from web_resolver import resolve_institution

  result = resolve_institution(
      extracted_name="VARANRAO THAPE HOMOEOPATHIC MEDICAL COLLEGE",
      extracted_address="SANGAMNER, AHMEDNAGAR"
  )
  # result = {
  #     "verified_college_name": "Vamanrao Ithape Homoeopathic Medical College & Hospital, Sangamner",
  #     "verified_college_address": "SANGAMNER, AHMEDNAGAR",   ← OCR address preserved
  #     "city": "Sangamner",
  #     "resolution_failed": False,
  #     "match_confidence": 87
  # }

Error Handling
--------------
Any failure (network, API, malformed JSON) causes the function to return the
original extracted values with resolution_failed=True and match_confidence=0.
The pipeline continues normally; the caller is responsible for writing the
"FAILED" flag into the Excel output.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from abc import ABC, abstractmethod

from google import genai
from google.genai import types
from dotenv import load_dotenv
from rapidfuzz import fuzz
from logger_config import logger
# from serpapi import GoogleSearch

load_dotenv()

# ---------------------------------------------------------------------------
# INSTITUTION CACHE  (local fuzzy-match layer to skip redundant API calls)
# ---------------------------------------------------------------------------

CACHE_PATH = "institution_cache.json"


def _load_cache() -> dict:
    """Load the institution cache from disk.  Returns {} on first run."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    """Persist the institution cache to disk."""
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"[Cache] Could not save cache: {exc}")


# ---------------------------------------------------------------------------
# ADDRESS HELPERS
# ---------------------------------------------------------------------------

# Matches "Phone No. ...", "Fax ...", "Email ...", "Website ..." and the
# text that follows them on the same token-run (up to a comma, newline, or end).
_ADDR_NOISE_RE = re.compile(
    r"\b(?:Phone\s*No\.?|Ph\.?|Fax|E-?mail|Website|Web)\b[^,\n;]*",
    re.IGNORECASE,
)
_EXTRA_SPACE_RE = re.compile(r"[ \t]{2,}")
_TRAILING_PUNCT_RE = re.compile(r"[\s,;:./\-]+$")
_LEADING_PUNCT_RE = re.compile(r"^[\s,;:./\-]+")


def clean_address(address: str) -> str:
    """
    Deterministic OCR address cleaner.

    Strips Phone/Fax/Email/Website fragments, duplicate PIN codes,
    and normalises whitespace.  Does NOT semantically rewrite the address.

    Parameters
    ----------
    address : str
        Raw OCR-extracted address string.

    Returns
    -------
    str
        Cleaned address string.
    """
    if not address:
        return address

    # 1. Remove phone/fax/email/website noise fragments
    text = _ADDR_NOISE_RE.sub("", address)

    # 2. Deduplicate 6-digit PINs — keep only the first occurrence
    seen_pins: set[str] = set()

    def _dedup_pin(m: re.Match) -> str:
        pin = m.group(0)
        if pin in seen_pins:
            return ""
        seen_pins.add(pin)
        return pin

    text = re.sub(r"\b\d{6}\b", _dedup_pin, text)

    # 3. Normalise whitespace and punctuation
    text = _EXTRA_SPACE_RE.sub(" ", text)
    text = _TRAILING_PUNCT_RE.sub("", text)
    text = _LEADING_PUNCT_RE.sub("", text)

    return text.strip()


# ---------------------------------------------------------------------------
# LOCALITY EXTRACTION
# ---------------------------------------------------------------------------

# Words that identify administrative/noise tokens, not useful locality names
_LOCALITY_NOISE_RE = re.compile(
    r"\b(maharashtra|m\.s\.|dist\.?|district|taluka|tq\.?|"
    r"village|vill\.?|post|p\.o\.|road|marg|lane|street|nagar)\b",
    re.IGNORECASE,
)
_PARENTHESES_RE = re.compile(r"\([^)]*\)")


def _extract_locality(address: str) -> str:
    """
    Extract the best geographic locality hint from a noisy OCR address.

    Heuristics are applied in priority order; the first one that yields a
    plausible result (≥ 3 alphabetic chars) is returned immediately.

    Priority order
    --------------
    1. PIN-anchored city  — word(s) immediately before a 6-digit PIN code,
       e.g. "Nagpur-440019" → "Nagpur",  "Jalna 431203" → "Jalna"
    2. District keyword   — token immediately after "Dist." / "District",
       e.g. "District Jalna" → "Jalna"
    3. State-stripped comma tokens — strip Maharashtra / M.S. / noise words
       from each comma-separated token and take the last meaningful one
    4. Parentheses removal + alphabetic scan — strip bracketed content
       (e.g. "(M.S.)") then pick the last long alphabetic word that is not
       a generic noise word

    Returns empty string if no locality can be extracted.
    """
    if not address:
        return ""

    # --- Heuristic 1: word(s) immediately before a 6-digit PIN ---
    # Handles: "Nagpur-440019", "Jalna 431203", "Ahmednagar-414001"
    pin_match = re.search(
        r"([A-Za-z][A-Za-z\s\-]{1,40})[\s\-–]+(\d{6})\b", address
    )
    if pin_match:
        # Take the last word of the group before the PIN
        raw = pin_match.group(1).strip()
        candidate = raw.split()[-1]
        candidate = _LOCALITY_NOISE_RE.sub("", candidate).strip()
        if len(candidate) >= 3 and candidate.isalpha():
            return candidate.title()

    # --- Heuristic 2: token immediately after "Dist." / "District" keyword ---
    dist_match = re.search(
        r"\b(?:dist\.?|district)\s+([A-Za-z][A-Za-z\s]{1,30})", address, re.IGNORECASE
    )
    if dist_match:
        # Take only the first word of whatever follows "Dist."
        candidate = dist_match.group(1).strip().split()[0]
        candidate = _LOCALITY_NOISE_RE.sub("", candidate).strip()
        if len(candidate) >= 3:
            return candidate.title()

    # --- Heuristic 3: state-stripped comma tokens ---
    # Strip parenthetical content, then split on commas/newlines
    cleaned = _PARENTHESES_RE.sub("", address)
    tokens = [t.strip() for t in re.split(r"[,\n]", cleaned) if t.strip()]
    # Walk backwards; for each token strip noise words and test alphabetic words
    for token in reversed(tokens):
        scrubbed = _LOCALITY_NOISE_RE.sub("", token).strip()
        # Find alphabetic-only words of length ≥ 3 within this token
        words = [w for w in scrubbed.split() if re.match(r"^[A-Za-z]{3,}$", w)]
        if words:
            return words[-1].title()

    # --- Heuristic 4: last meaningful alphabetic word in the full address ---
    noise_words = {
        "maharashtra", "district", "taluka", "village", "post", "road",
        "nagar", "marg", "lane", "street", "college", "medical", "hospital",
        "and", "the", "of", "for",
    }
    all_alpha = re.findall(r"\b[A-Za-z]{4,}\b", address)
    for word in reversed(all_alpha):
        if word.lower() not in noise_words:
            return word.title()

    return ""


# ---------------------------------------------------------------------------
# QUERY BUILDER  (extensible — never touches resolve_institution())
# ---------------------------------------------------------------------------

def _build_queries(name: str, address: str) -> list[str]:
    """
    Return a priority-ordered list of search query strings.

    The caller iterates this list and stops at the first query that returns
    search results.  To add new query strategies — abbreviation removal,
    stop-word stripping, trust-name removal, BHMS/BAMS suffix removal, etc.
    — simply append new strings here.  resolve_institution() never needs
    to change.

    Current tiers
    -------------
    Tier 1  name + locality + "Maharashtra"    (most specific)
    Tier 2  name + locality
    Tier 3  name alone                         (widest net / last resort)
    """
    locality = _extract_locality(address)

    queries: list[str] = []

    # Tier 1: name + locality + state
    if locality:
        queries.append(f"{name} {locality} Maharashtra")
    else:
        # No locality found — still try with state as the anchor
        queries.append(f"{name} Maharashtra")

    # Tier 2: name + locality only (drop state to widen slightly)
    if locality:
        queries.append(f"{name} {locality}")

    # Tier 3: name alone — always the ultimate fallback
    queries.append(name)

    # --------------------------------------------------------------------------
    # Future tiers can be appended here without touching resolve_institution().
    # Examples:
    #   queries.append(_remove_trust_prefix(name))
    #   queries.append(_remove_degree_suffix(name))
    #   queries.append(_expand_abbreviations(name))
    # --------------------------------------------------------------------------

    return queries


# ---------------------------------------------------------------------------
# CONFIDENCE SCORING
# ---------------------------------------------------------------------------

# Confidence bands
_CONFIDENCE_BANDS = [
    (90, "Excellent"),
    (75, "Good"),
    (55, "Weak"),
    (0,  "Reject"),
]
_CONFIDENCE_REJECT_THRESHOLD = 55


def _compute_confidence(resolved_name: str, extracted_name: str) -> int:
    """
    Compare the Gemini-resolved college name against the original OCR name.

    Uses rapidfuzz ``token_set_ratio`` (case-insensitive) rather than
    ``token_sort_ratio``.  Token-set ratio scores 100 whenever the shorter
    string's tokens are a subset of the longer string's tokens — exactly
    what we want when the resolved name extends the OCR name with a city
    or hospital suffix (e.g. "XYZ Medical College" → "XYZ Medical College
    & Hospital, Sangamner" still scores 100).

    Parameters
    ----------
    resolved_name : str
        College name selected / canonicalised by Gemini.
    extracted_name : str
        Original OCR-extracted name from Qwen.

    Returns
    -------
    int
        Confidence score 0–100.
    """
    if not resolved_name or not extracted_name:
        return 0
    return round(fuzz.token_set_ratio(resolved_name.lower(), extracted_name.lower()))


def _confidence_label(score: int) -> str:
    """Return a human-readable label for a confidence score."""
    for threshold, label in _CONFIDENCE_BANDS:
        if score >= threshold:
            return label
    return "Reject"


# ---------------------------------------------------------------------------
# SEARCH PROVIDER ABSTRACTION
# ---------------------------------------------------------------------------

# class SearchProvider(ABC):
#     """Abstract search interface. Implement this to swap search backends."""
# 
#     @abstractmethod
#     def perform_search(self, query: str) -> list[dict]:
#         """
#         Execute a web search and return up to 5 organic results.
# 
#         Each result dict must contain:
#             title   : str
#             snippet : str
#             url     : str
#         """
#         raise NotImplementedError
# 
# 
# class SerpApiProvider(SearchProvider):
#     """
#     Concrete search provider backed by SerpAPI (Google Search).
# 
#     To replace with Brave / Bing / Tavily:
#       1. Create a new subclass of SearchProvider.
#       2. Change the one-line wiring in resolve_institution().
#     """
# 
#     MAX_RESULTS = 5
# 
#     def __init__(self, api_key: str):
#         self._api_key = api_key
# 
#     def perform_search(self, query: str) -> list[dict]:
#         params = {
#             "q": query,
#             "api_key": self._api_key,
#             "num": 10,          # request a few extra so filtering still gives 5
#             "hl": "en",
#             "gl": "in",         # India locale for better relevance
#         }
# 
#         search = GoogleSearch(params)
#         raw = search.get_dict()
# 
#         organic = raw.get("organic_results", [])
# 
#         results = []
#         for item in organic:
#             results.append({
#                 "title":   item.get("title", ""),
#                 "snippet": item.get("snippet", ""),
#                 "url":     item.get("link", ""),
#             })
#             if len(results) >= self.MAX_RESULTS:
#                 break
# 
#         return results


# ---------------------------------------------------------------------------
# LLM CLIENT ABSTRACTION
# ---------------------------------------------------------------------------

class LLMClient(ABC):
    """Abstract LLM interface. Implement this to swap AI backends."""

    @abstractmethod
    def resolve(
        self,
        extracted_name: str,
        extracted_address: str,
    ) -> dict:
        """
        Given the extracted college name, address, and top search results,
        return a dict with keys:
            verified_college_name : str   — canonicalised institution name
            city                  : str   — city extracted from the winning result

        Note: verified_college_address is intentionally NOT returned here.
        The OCR-extracted address is authoritative and is handled by
        resolve_institution() after clean_address() post-processing.
        """
        raise NotImplementedError


class GeminiClient(LLMClient):
    """
    Concrete LLM client backed by Google Gemini.

    To replace with GPT / Claude / Ollama:
      1. Create a new subclass of LLMClient.
      2. Change the one-line wiring in resolve_institution().
    """

    # MODEL_NAME = "gemini-2.5-flash-lite"
    MODEL_NAME = "gemini-2-flash"


    _SYSTEM_PROMPT = """\
You are an institution entity-resolution assistant for Indian medical colleges.

You will receive:
  1. An extracted college name (possibly noisy / misspelled).
  2. An extracted college address (possibly noisy).

Your job:
  - Find the official institution name and full, official postal address for this college in Maharashtra, India.
  - Return ONLY strict JSON. No markdown codeblocks. No explanation. No extra keys.
  - JSON schema:
      {
        "verified_college_name": "<Verified, official institution name>",
        "verified_college_address": "<Verified, full postal address of the institution>"
      }
"""

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    def _build_user_message(
        self,
        extracted_name: str,
        extracted_address: str,
    ) -> str:
        lines = [
            f"Extracted college name: {extracted_name}",
            f"Extracted college address: {extracted_address or '(not available)'}",
            ""
        ]
        return "\n".join(lines)

    # Common search-result title suffixes that are noise, not institution names.
    _TITLE_NOISE = re.compile(
        r"\s*[\-\u2013|]\s*(wikipedia|official (site|website)|home page|about|"
        r"admissions?|contact|facebook|justdial|sulekha|indiamart)\.?\s*$",
        re.IGNORECASE,
    )

    GEMINI_MODELS = [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3-flash",
    ]

    def resolve(
        self,
        extracted_name: str,
        extracted_address: str,
    ) -> dict:
        user_message = self._build_user_message(
            extracted_name, extracted_address
        )

        last_exc: Exception | None = None

        # 1. Google Gemini SDK Fallback Sequence
        for i, model_name in enumerate(self.GEMINI_MODELS):
            if i == 0:
                logger.info(f"• Trying {model_name}")
            else:
                logger.info(f"• Switching to {model_name}")
            try:
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=self._SYSTEM_PROMPT,
                        temperature=0.0,
                        tools=[{"google_search": {}}],
                    ),
                )
                raw_text = response.text.strip()
                return self._parse_json_response(raw_text, extracted_name)
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                if "503" in err_str or "unavailable" in err_str or "429" in err_str:
                    logger.info("• Quota exceeded")
                    logger.debug(
                        f"[Gemini] {model_name} hit transient/capacity error: {exc}."
                    )
                    continue
                logger.debug(f"[Gemini] {model_name} failed: {exc}.")
                logger.info(f"• {model_name} failed")
                continue

        # 2. OpenRouter Fallback
        logger.info("• Falling back to OpenRouter")
        logger.debug("[Resolver] All Google models failed. Falling back to OpenRouter (openrouter/free)...")
        try:
            raw_text = self._call_openrouter(user_message)
            return self._parse_json_response(raw_text, extracted_name)
        except Exception as exc:
            logger.error(f"[Resolver] OpenRouter fallback also failed: {exc}")
            raise last_exc or RuntimeError("All resolution models failed.")

    def _parse_json_response(self, raw_text: str, extracted_name: str) -> dict:
        try:
            gemini_data = json.loads(raw_text)
            if not isinstance(gemini_data, dict):
                logger.error("[Resolver] LLM returned non-dict JSON")
                gemini_data = {}
        except json.JSONDecodeError as e:
            logger.error(f"[Resolver] LLM JSON parsing failed: {e}")
            gemini_data = {}

        verified_name = str(gemini_data.get("verified_college_name") or extracted_name)
        verified_address = str(gemini_data.get("verified_college_address") or "")

        # Strip common search-result title noise (" - Wikipedia", " | Official Site")
        clean_name = self._TITLE_NOISE.sub("", verified_name).strip()

        return {
            "verified_college_name": clean_name,
            "verified_college_address": verified_address,
        }

    def _call_openrouter(self, user_message: str) -> str:
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if not openrouter_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment.")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://mahabocw-pipeline.local",
            "X-Title": "MAHABOCW IDP",
        }

        payload = {
            "model": "openrouter/free",
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            if content.startswith("```json"):
                content = (
                    content.replace("```json\n", "")
                           .replace("```json", "")
                           .replace("\n```", "")
                           .replace("```", "")
                )
            return content.strip()


# ---------------------------------------------------------------------------
# CITY-APPEND HELPER
# ---------------------------------------------------------------------------

def _append_city(college_name: str, city: str) -> str:
    """
    Append the city to the college name if it is not already present.

    Rules:
      - Only the city is appended (never district / state / PIN / taluka).
      - Comparison is case-insensitive.
      - If the city string is empty or already contained in the name, return as-is.
    """
    if not city:
        return college_name

    # Case-insensitive check — does the name already contain the city?
    if city.lower() in college_name.lower():
        return college_name

    return f"{college_name}, {city}"


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def resolve_institution(
    extracted_name: str,
    extracted_address: str,
) -> dict:
    """
    Resolve the real institution from the noisy Qwen-extracted values.

    The OCR-extracted address is the source of truth.  The web resolver
    canonicalises the institution name only.

    Parameters
    ----------
    extracted_name : str
        College name as produced by the Qwen LLM extraction stage.
    extracted_address : str
        College address as produced by the Qwen LLM extraction stage.
        Preserved and cleaned; never overwritten by web search snippets.

    Returns
    -------
    dict with keys:
        verified_college_name    : str   — official name with city appended
        verified_college_address : str   — cleaned OCR address (authoritative)
        city                     : str   — city only
        resolution_failed        : bool  — True if online verification failed
        match_confidence         : int   — rapidfuzz token_sort_ratio (0-100)
    """
    # --- Wire in the concrete providers (single location for future swaps) ---
    # search_provider: SearchProvider = SerpApiProvider(
    #     api_key=os.environ["SERPAPI_API_KEY"]
    # )
    llm_client: LLMClient = GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"]
    )
    # -------------------------------------------------------------------------

    # Fallback address in case Gemini fails
    cleaned_ocr_address = clean_address(extracted_address)

    fallback = {
        "verified_college_name":    extracted_name,
        "verified_college_address": cleaned_ocr_address,
        "city":                     "",
        "resolution_failed":        True,
        "match_confidence":         0,
    }

    # -----------------------------------------------------------------------
    # Step 0 — Fuzzy cache lookup (skip Google + Gemini for known institutions)
    # -----------------------------------------------------------------------
    norm_key = extracted_name.lower().strip()
    cache = _load_cache()

    best_cache_score = 0
    best_cache_key   = None
    for cached_key in cache:
        score = fuzz.token_sort_ratio(norm_key, cached_key)
        if score > best_cache_score:
            best_cache_score = score
            best_cache_key   = cached_key

    if best_cache_score > 90 and best_cache_key is not None:
        cached = cache[best_cache_key]
        logger.info("• Cache hit")
        logger.debug(f"[Resolver] Cache HIT (score={best_cache_score}) -> {cached['official_name']}")
        return {
            "verified_college_name":    cached["official_name"],
            "verified_college_address": cached.get("official_address", cleaned_ocr_address),
            "city":                     cached.get("city", ""),
            "resolution_failed":        False,
            "match_confidence":         100,  # trusted cache entry
            "via_cache":                True,
        }

    logger.info("• Cache miss")
    logger.debug(f"[Resolver] Cache MISS (best_score={best_cache_score}). Proceeding to web search.")

    # -----------------------------------------------------------------------
    # Step 1 & 2 — Ask the LLM to directly search and identify the institution
    # -----------------------------------------------------------------------
    try:
        logger.debug("[Resolver] Sending candidates to Gemini with Native Search Grounding...")
        llm_result = llm_client.resolve(extracted_name, extracted_address)

    except json.JSONDecodeError as exc:
        logger.debug(f"[Resolver] Gemini returned malformed JSON: {exc}")
        return fallback

    except Exception as exc:
        logger.debug(f"[Resolver] Gemini call failed: {exc}")
        return fallback

    # -----------------------------------------------------------------------
    # Step 3 — Validate LLM response has required keys
    # -----------------------------------------------------------------------
    if "verified_college_name" not in llm_result:
        logger.debug(f"[Resolver] Gemini response missing required keys: {llm_result}")
        return fallback

    # -----------------------------------------------------------------------
    # Step 4 — Compute entity resolution confidence
    # -----------------------------------------------------------------------
    verified_name = llm_result.get("verified_college_name", "").strip()
    verified_address = llm_result.get("verified_college_address", "").strip()
    city = ""  # We no longer extract city separately

    match_confidence = _compute_confidence(verified_name, extracted_name)
    label            = _confidence_label(match_confidence)
    logger.debug(f"[Resolver] Match confidence: {match_confidence} ({label}) — "
          f"'{verified_name}' vs '{extracted_name}'")

    # Reject low-confidence matches to avoid polluting output with bad candidates
    if match_confidence < _CONFIDENCE_REJECT_THRESHOLD:
        logger.debug(
            f"[Resolver] Confidence {match_confidence} < {_CONFIDENCE_REJECT_THRESHOLD} "
            "(Reject threshold). Returning fallback."
        )
        return {**fallback, "match_confidence": match_confidence}

    # -----------------------------------------------------------------------
    # Step 5 — Assemble final result
    # -----------------------------------------------------------------------
    # Native search retrieves the full address, so we prefer it.
    final_name    = verified_name
    final_address = verified_address if verified_address else cleaned_ocr_address

    result = {
        "verified_college_name":    final_name,
        "verified_college_address": final_address,
        "city":                     "",  # We don't strictly need city appended anymore if final_name is already accurate
        "resolution_failed":        False,
        "match_confidence":         match_confidence,
    }

    # -----------------------------------------------------------------------
    # Step 6 — Persist to cache ONLY on high-quality matches
    # -----------------------------------------------------------------------
    if match_confidence >= _CONFIDENCE_REJECT_THRESHOLD:
        cache[norm_key] = {
            "official_name": final_name,
            "official_address": final_address,
            "city":          city,
        }
        _save_cache(cache)
        logger.debug(f"[Cache] Saved: {norm_key!r} (confidence={match_confidence})")

    logger.debug("[Resolver] Institution resolved.")
    logger.debug(f"Verified College: {final_name}")

    return result

"""
web_resolver.py
---------------
Online Institution Resolution stage for the MAHABOCW Medical Scholarship
Verification pipeline.

Responsibility
--------------
Takes the noisy college name and address produced by the Qwen OCR extraction
stage and resolves them to the real, official institution name and address
by performing a Google Search and asking Gemini to rank the results.

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

Usage
-----
  from web_resolver import resolve_institution

  result = resolve_institution(
      extracted_name="VARANRAO THAPE HOMOEOPATHIC MEDICAL COLLEGE",
      extracted_address="SANGAMNER, AHMEDNAGAR"
  )
  # result = {
  #     "verified_college_name": "Vamanrao Ithape Homoeopathic Medical College & Hospital, Sangamner",
  #     "verified_college_address": "Ahmednagar Road, Sangamner, Maharashtra",
  #     "city": "Sangamner",
  #     "resolution_failed": False
  # }

Error Handling
--------------
Any failure (network, API, malformed JSON) causes the function to return the
original extracted values with resolution_failed=True.
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
from serpapi import GoogleSearch

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
        print(f"[Cache] Could not save cache: {exc}")

# ---------------------------------------------------------------------------
# SEARCH PROVIDER ABSTRACTION
# ---------------------------------------------------------------------------

class SearchProvider(ABC):
    """Abstract search interface. Implement this to swap search backends."""

    @abstractmethod
    def perform_search(self, query: str) -> list[dict]:
        """
        Execute a web search and return up to 5 organic results.

        Each result dict must contain:
            title   : str
            snippet : str
            url     : str
        """
        raise NotImplementedError


class SerpApiProvider(SearchProvider):
    """
    Concrete search provider backed by SerpAPI (Google Search).

    To replace with Brave / Bing / Tavily:
      1. Create a new subclass of SearchProvider.
      2. Change the one-line wiring in resolve_institution().
    """

    MAX_RESULTS = 5

    def __init__(self, api_key: str):
        self._api_key = api_key

    def perform_search(self, query: str) -> list[dict]:
        params = {
            "q": query,
            "api_key": self._api_key,
            "num": 10,          # request a few extra so filtering still gives 5
            "hl": "en",
            "gl": "in",         # India locale for better relevance
        }

        search = GoogleSearch(params)
        raw = search.get_dict()

        organic = raw.get("organic_results", [])

        results = []
        for item in organic:
            results.append({
                "title":   item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "url":     item.get("link", ""),
            })
            if len(results) >= self.MAX_RESULTS:
                break

        return results


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
        search_results: list[dict],
    ) -> dict:
        """
        Given the extracted college name, address, and top search results,
        return a dict with keys:
            verified_college_name    : str
            verified_college_address : str
            city                     : str
        """
        raise NotImplementedError


class GeminiClient(LLMClient):
    """
    Concrete LLM client backed by Google Gemini.

    To replace with GPT / Claude / Ollama:
      1. Create a new subclass of LLMClient.
      2. Change the one-line wiring in resolve_institution().
    """

    MODEL_NAME = "gemini-2.5-flash-lite"

    _SYSTEM_PROMPT = """\
You are an institution entity-resolution assistant.

You will receive:
  1. An extracted college name (possibly noisy / misspelled).
  2. An extracted college address (possibly noisy or incomplete).
  3. Up to 5 numbered Google search results, each with a title, snippet, and URL.

Your job:
  - Identify which search result most closely matches the extracted institution.
  - You MUST select ONE of the provided search results. Do NOT invent names or
    addresses that do not appear in the search results.
  - Copy the exact title and snippet text from the winning result into the output.
  - Extract the city name from the winning result's title or snippet.

Rules:
  - Return ONLY strict JSON. No markdown. No explanation. No extra keys.
  - JSON schema:
      {
        "winning_title":   "<Exact title string from the best matching result>",
        "winning_snippet": "<Exact snippet string from the best matching result>",
        "city": "<City only — not district, not state, not PIN code>"
      }
  - If none of the results match with reasonable confidence, copy the extracted
    name as winning_title and extracted address as winning_snippet.
"""

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    def _build_user_message(
        self,
        extracted_name: str,
        extracted_address: str,
        search_results: list[dict],
    ) -> str:
        lines = [
            f"Extracted college name: {extracted_name}",
            f"Extracted college address: {extracted_address or '(not available)'}",
            "",
            "Search results:",
        ]
        for i, r in enumerate(search_results, 1):
            lines.append(f"  [{i}] Title:   {r['title']}")
            lines.append(f"       Snippet: {r['snippet']}")
            lines.append(f"       URL:     {r['url']}")
            lines.append("")

        return "\n".join(lines)

    # Common search-result title suffixes that are noise, not institution names.
    _TITLE_NOISE = re.compile(
        r"\s*[\-\u2013|]\s*(wikipedia|official (site|website)|home page|about|"
        r"admissions?|contact|facebook|justdial|sulekha|indiamart)\.?\s*$",
        re.IGNORECASE,
    )

    GEMINI_MODELS = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]

    def resolve(
        self,
        extracted_name: str,
        extracted_address: str,
        search_results: list[dict],
    ) -> dict:
        user_message = self._build_user_message(
            extracted_name, extracted_address, search_results
        )

        last_exc: Exception | None = None
        
        # 1. Google Gemini SDK Fallback Sequence
        for model_name in self.GEMINI_MODELS:
            print(f"[Gemini] Attempting resolution with {model_name}...")
            try:
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=self._SYSTEM_PROMPT,
                        temperature=0.0,
                        response_mime_type="application/json",
                        response_schema={
                            "type": "object",
                            "properties": {
                                "winning_title":   {"type": "string"},
                                "winning_snippet": {"type": "string"},
                                "city":            {"type": "string"},
                            },
                            "required": [
                                "winning_title",
                                "winning_snippet",
                                "city",
                            ],
                        }
                    ),
                )
                raw_text = response.text.strip()
                return self._parse_json_response(raw_text, extracted_name, extracted_address)
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                if "503" in err_str or "unavailable" in err_str or "429" in err_str:
                    print(f"[Gemini] {model_name} hit transient/capacity error: {exc}. Trying next model...")
                    continue
                print(f"[Gemini] {model_name} failed: {exc}. Trying next model...")
                continue

        # 2. OpenRouter Fallback
        print("[Resolver] All Google models failed. Falling back to OpenRouter (openrouter/free)...")
        try:
            raw_text = self._call_openrouter(user_message)
            return self._parse_json_response(raw_text, extracted_name, extracted_address)
        except Exception as exc:
            print(f"[Resolver] OpenRouter fallback also failed: {exc}")
            raise last_exc or RuntimeError("All resolution models failed.")

    def _parse_json_response(self, raw_text: str, extracted_name: str, extracted_address: str) -> dict:
        gemini_data = json.loads(raw_text)
        winning_title   = gemini_data.get("winning_title",   extracted_name)
        winning_snippet = gemini_data.get("winning_snippet", extracted_address)
        city            = gemini_data.get("city", "")

        # Strip common search-result title noise (" - Wikipedia", " | Official Site")
        clean_name = self._TITLE_NOISE.sub("", winning_title).strip()

        return {
            "verified_college_name":    clean_name,
            "verified_college_address": winning_snippet,
            "city":                     city,
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
            "X-Title": "MAHABOCW IDP"
        }
        
        payload = {
            "model": "openrouter/free",
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        }
        
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            content = result["choices"][0]["message"]["content"]
            if content.startswith("```json"):
                content = content.replace("```json\n", "").replace("```json", "").replace("\n```", "").replace("```", "")
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

    Parameters
    ----------
    extracted_name : str
        College name as produced by the Qwen LLM extraction stage.
    extracted_address : str
        College address as produced by the Qwen LLM extraction stage.

    Returns
    -------
    dict with keys:
        verified_college_name    : str   — official name with city appended
        verified_college_address : str   — official address
        city                     : str   — city only
        resolution_failed        : bool  — True if online verification failed
    """
    # --- Wire in the concrete providers (single location for future swaps) ---
    search_provider: SearchProvider = SerpApiProvider(
        api_key=os.environ["SERPAPI_API_KEY"]
    )
    llm_client: LLMClient = GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"]
    )
    # -------------------------------------------------------------------------

    fallback = {
        "verified_college_name":    extracted_name,
        "verified_college_address": extracted_address,
        "city":                     "",
        "resolution_failed":        True,
    }

    # -----------------------------------------------------------------------
    # Step 0 -- Fuzzy cache lookup (skip Google + Gemini for known institutions)
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
        print(f"[Resolver] Cache HIT (score={best_cache_score}) -> {cached['official_name']}")
        return {
            "verified_college_name":    cached["official_name"],
            "verified_college_address": cached["official_address"],
            "city":                     "",
            "resolution_failed":        False,
        }

    print(f"[Resolver] Cache MISS (best_score={best_cache_score}). Proceeding to web search.")

    try:
        # Step 1 -- Build and execute search query
        query = f'"{extracted_name}" "{extracted_address}"'
        print(f"[Resolver] Searching Google...")

        search_results = search_provider.perform_search(query)

        if not search_results:
            print("[Resolver] No search results returned. Using extracted values.")
            return fallback

        print(f"[Resolver] Retrieved {len(search_results)} search result(s).")

    except Exception as exc:
        print(f"[Resolver] Search failed: {exc}")
        print("[Resolver] Online verification unavailable. Using extracted values.")
        return fallback

    try:
        # Step 2 — Ask the LLM to rank results and identify the institution
        print("[Resolver] Sending candidates to Gemini...")
        llm_result = llm_client.resolve(extracted_name, extracted_address, search_results)

    except json.JSONDecodeError as exc:
        print(f"[Resolver] Gemini returned malformed JSON: {exc}")
        print("[Resolver] Online verification unavailable. Using extracted values.")
        return fallback

    except Exception as exc:
        print(f"[Resolver] Gemini call failed: {exc}")
        print("[Resolver] Online verification unavailable. Using extracted values.")
        return fallback

    # Step 3 — Validate the LLM response contains the required keys
    required_keys = {"verified_college_name", "verified_college_address", "city"}
    if not required_keys.issubset(llm_result.keys()):
        print(f"[Resolver] Gemini response missing required keys: {llm_result}")
        print("[Resolver] Online verification unavailable. Using extracted values.")
        return fallback

    # Step 4 -- Append city to the college name (Python-enforced, not Gemini)
    verified_name = llm_result["verified_college_name"].strip()
    city          = llm_result["city"].strip()

    final_name    = _append_city(verified_name, city)
    final_address = llm_result["verified_college_address"].strip()

    result = {
        "verified_college_name":    final_name,
        "verified_college_address": final_address,
        "city":                     city,
        "resolution_failed":        False,
    }

    # Step 5 -- Persist to cache so future lookups skip Google + Gemini
    cache[norm_key] = {
        "official_name":    final_name,
        "official_address": final_address,
    }
    _save_cache(cache)
    print(f"[Cache] Saved: {norm_key!r}")

    print("[Resolver] Institution resolved.")
    print(f"Verified College: {final_name}")

    return result

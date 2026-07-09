"""
Resolve noisy OCR college names to one stable official college record.

The resolver returns a canonical college name with city appended and one
canonical address. The cache stores that full resolved record so repeated
claims for the same college write the same name and address to Excel.
"""

from __future__ import annotations


class LLMUnverifiableError(ValueError):
    """Raised when the LLM explicitly returns verified=false (not a parse error)."""


import json
import os
import re
import urllib.request

from dotenv import load_dotenv
from google import genai
from google.genai import types
from rapidfuzz import fuzz

from logger_config import logger

load_dotenv()

CACHE_PATH = "institution_cache.json"
CACHE_HIT_THRESHOLD = 90
CONFIDENCE_REJECT_THRESHOLD = 75


_ADDR_NOISE_RE = re.compile(
    r"\b(?:Phone\s*No\.?|Ph\.?|Fax|E-?mail|Website|Web)\b[^,\n;]*",
    re.IGNORECASE,
)
_EXTRA_SPACE_RE = re.compile(r"[ \t]{2,}")
_COMMA_SPACE_RE = re.compile(r"\s*,\s*")
_DUP_COMMA_RE = re.compile(r"(?:,\s*){2,}")
_TRAILING_PUNCT_RE = re.compile(r"[\s,;:./\-]+$")
_LEADING_PUNCT_RE = re.compile(r"^[\s,;:./\-]+")
_PIN_RE = re.compile(r"\b\d{6}\b")
_TITLE_NOISE_RE = re.compile(
    r"\s*[\-\u2013|]\s*(wikipedia|official (site|website)|home page|about|"
    r"admissions?|contact|facebook|justdial|sulekha|indiamart)\.?\s*$",
    re.IGNORECASE,
)
_GENERIC_NAME_RE = re.compile(
    r"^(?:dr\.?\s*)?(?:ayurved(?:ic)?|homeo(?:e)?opathic|medical|dental|"
    r"nursing|pharmacy|college|hospital|research|institute|and|&|\s)+$",
    re.IGNORECASE,
)
_LOCALITY_NOISE_RE = re.compile(
    r"\b(maharashtra|m\.s\.|dist\.?|district|taluka|tq\.?|village|vill\.?|"
    r"post|p\.o\.|road|marg|lane|street|nagar|college|medical|hospital|"
    r"institute|research|behind|near)\b",
    re.IGNORECASE,
)


SYSTEM_PROMPT = """\
You are resolving OCR-extracted college records for a government claim audit.

Accuracy of the college identity is the highest priority. Do not guess.

Input:
- extracted_college_name: noisy OCR/LLM output from a student document.
- extracted_college_address: noisy OCR/LLM output from the same document.

Task:
1. Use Google Search grounding to identify the single official institution.
2. Match the institution using BOTH name and address/locality. The address or
   city must be compatible with the extracted address.
3. Return the official college/institution name only. Do not return trust names,
   page titles, department names, course names, generic names, or search-result
   snippets as the college name.
4. Return the official postal address for that same institution. Do not return
   a website description, search snippet, admission text, phone/email-only text,
   or an address for a different branch.
5. Return city as one city/town/locality only, with no state, district label,
   taluka label, PIN code, punctuation, or extra words.
6. If the exact institution cannot be verified, set verified=false and leave
   verified_college_name, verified_college_address, and city as empty strings.

Strict output:
- Return only valid JSON.
- No markdown.
- No comments.
- No extra keys.
- JSON schema:
{
  "verified": true,
  "verified_college_name": "Official institution name without city suffix",
  "verified_college_address": "Official postal address",
  "city": "City"
}
"""


GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash"
]


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"[Cache] Could not save cache: {exc}")


def _normalise_spaces(text: str) -> str:
    return _EXTRA_SPACE_RE.sub(" ", (text or "").replace("\n", " ")).strip()


def _normalise_key(text: str) -> str:
    text = _normalise_spaces(text).lower()
    text = re.sub(r"[^\w\s&]", " ", text)
    return _EXTRA_SPACE_RE.sub(" ", text).strip()


def clean_address(address: str) -> str:
    if not address:
        return ""

    text = _ADDR_NOISE_RE.sub("", address)

    seen_pins: set[str] = set()

    def dedup_pin(match: re.Match) -> str:
        pin = match.group(0)
        if pin in seen_pins:
            return ""
        seen_pins.add(pin)
        return pin

    text = _PIN_RE.sub(dedup_pin, text)
    text = _normalise_spaces(text)
    text = _COMMA_SPACE_RE.sub(", ", text)
    text = _DUP_COMMA_RE.sub(", ", text)
    text = _TRAILING_PUNCT_RE.sub("", text)
    text = _LEADING_PUNCT_RE.sub("", text)
    return text.strip()


def _clean_name(name: str) -> str:
    name = _TITLE_NOISE_RE.sub("", name or "")
    name = _normalise_spaces(name)
    return _TRAILING_PUNCT_RE.sub("", name).strip()


def _extract_city_from_address(address: str) -> str:
    if not address:
        return ""

    pin_match = re.search(r"([A-Za-z][A-Za-z\s\-.]{1,50})[\s\-]+(\d{6})\b", address)
    if pin_match:
        words = re.findall(r"[A-Za-z]{3,}", pin_match.group(1))
        for word in reversed(words):
            if not _LOCALITY_NOISE_RE.fullmatch(word):
                return word.title()

    district_match = re.search(
        r"\b(?:dist\.?|district)\s*[:\-]?\s*([A-Za-z][A-Za-z\s]{1,30})",
        address,
        re.IGNORECASE,
    )
    if district_match:
        words = re.findall(r"[A-Za-z]{3,}", district_match.group(1))
        if words:
            return words[0].title()

    tokens = [t.strip() for t in re.split(r"[,;]", address) if t.strip()]
    for token in reversed(tokens):
        words = re.findall(r"[A-Za-z]{3,}", _LOCALITY_NOISE_RE.sub("", token))
        if words:
            return words[-1].title()

    return ""


def _clean_city(city: str, address: str) -> str:
    words = re.findall(r"[A-Za-z]{3,}", city or "")
    city_words = [word.title() for word in words if not _LOCALITY_NOISE_RE.fullmatch(word)]
    if city_words:
        return " ".join(city_words[:3])
    return _extract_city_from_address(address)


def _append_city(college_name: str, city: str) -> str:
    college_name = _clean_name(college_name)
    city = _clean_city(city, "")
    if not college_name or not city:
        return college_name
    if re.search(rf"\b{re.escape(city)}\b", college_name, re.IGNORECASE):
        return college_name
    return f"{college_name}, {city}"


def _is_generic_name(name: str) -> bool:
    cleaned = _normalise_key(name)
    if len(cleaned.split()) < 4:
        return True
    return bool(_GENERIC_NAME_RE.fullmatch(cleaned))


def _compute_confidence(resolved_name: str, extracted_name: str) -> int:
    if not resolved_name or not extracted_name:
        return 0
    return round(fuzz.token_set_ratio(resolved_name.lower(), extracted_name.lower()))


def _cache_record_is_complete(record: dict) -> bool:
    return bool(
        record.get("official_name")
        and record.get("official_address")
        and record.get("city")
    )


def _find_cache_record(
    cache: dict,
    extracted_name: str,
    extracted_address: str = "",
) -> tuple[str | None, dict | None, int]:
    norm_key = _normalise_key(extracted_name)
    best_key = None
    best_score = 0

    for cached_key, record in cache.items():
        if not _cache_record_is_complete(record):
            continue
        aliases = [cached_key, record.get("official_name", ""), *record.get("aliases", [])]
        score = max(fuzz.token_sort_ratio(norm_key, _normalise_key(alias)) for alias in aliases)
        if score > best_score:
            best_key = cached_key
            best_score = score

    if best_key and best_score >= CACHE_HIT_THRESHOLD:
        # City guard: before accepting the fuzzy name hit, ensure the cached
        # city is at least loosely present in the incoming OCR address.  This
        # prevents colleges that share a near-identical name in *different*
        # towns (common in Maharashtra) from silently merging into the same
        # cache entry and writing the wrong city's address onto a claim.
        cached_city = (cache[best_key].get("city") or "").strip()
        if cached_city and extracted_address:
            ocr_city_guess = _extract_city_from_address(extracted_address)
            # Accept if either:
            #   (a) cached city appears verbatim in the raw OCR address, or
            #   (b) fuzzy match between cached city and OCR-extracted city ≥ 80
            city_in_addr = cached_city.lower() in extracted_address.lower()
            city_fuzzy_ok = bool(
                ocr_city_guess
                and fuzz.token_sort_ratio(
                    cached_city.lower(), ocr_city_guess.lower()
                ) >= 80
            )
            if not (city_in_addr or city_fuzzy_ok):
                logger.debug(
                    f"[Cache] Name score={best_score} but city mismatch: "
                    f"cached={cached_city!r} vs ocr_guess={ocr_city_guess!r} "
                    f"(addr={extracted_address!r}) — ignoring cache hit."
                )
                return None, None, round(best_score)
        return best_key, cache[best_key], round(best_score)
    return None, None, round(best_score)


def _build_user_message(extracted_name: str, extracted_address: str) -> str:
    payload = {
        "extracted_college_name": extracted_name,
        "extracted_college_address": extracted_address,
    }
    return json.dumps(payload, ensure_ascii=False)


def _parse_model_json(raw_text: str) -> dict:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("LLM returned an empty response")
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("LLM returned non-object JSON")
    # Distinguish an explicit "I cannot verify" response from other failures so
    # callers can log it at DEBUG level and fall through to the normal fallback
    # without surfacing a spurious ERROR entry in the log.
    if data.get("verified") is not True:
        raise LLMUnverifiableError(
            "LLM could not verify institution (verified=false in response)"
        )

    required = ("verified_college_name", "verified_college_address", "city")
    missing = [key for key in required if not str(data.get(key) or "").strip()]
    if missing:
        raise ValueError(f"LLM JSON missing required values: {', '.join(missing)}")

    return data


class GeminiResolver:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    def resolve(self, extracted_name: str, extracted_address: str) -> dict:
        user_message = _build_user_message(extracted_name, extracted_address)
        last_exc: Exception | None = None

        for i, model_name in enumerate(GEMINI_MODELS):
            logger.info(f"- {'Trying' if i == 0 else 'Switching to'} {model_name}")
            try:
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.0,
                        tools=[{"google_search": {}}],
                    ),
                )
                return _parse_model_json(response.text or "")
            except Exception as exc:
                last_exc = exc
                err = str(exc).lower()
                if "429" in err or "quota" in err or "resource_exhausted" in err:
                    logger.info("- Gemini quota/rate limit hit")
                elif "503" in err or "unavailable" in err:
                    logger.info("- Gemini temporarily unavailable")
                else:
                    logger.info(f"- {model_name} failed")
                logger.debug(f"[Gemini] {model_name} failed: {exc}")

        logger.info("- Falling back to OpenRouter")
        try:
            return _parse_model_json(self._call_openrouter(user_message))
        except Exception as exc:
            logger.error(f"[Resolver] OpenRouter fallback also failed: {exc}")
            raise last_exc or RuntimeError("All resolution models failed.")

    def _call_openrouter(self, user_message: str) -> str:
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if not openrouter_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment.")

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps({
                "model": "openrouter/auto",
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://mahabocw-pipeline.local",
                "X-Title": "MAHABOCW IDP",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = (
                result.get("choices", [{}])[0]
                .get("message", {})
                .get("content")
            )
            if not content or not str(content).strip():
                raise ValueError(
                    "OpenRouter returned an empty or malformed response "
                    f"(choices={result.get('choices')})"
                )
            return str(content).strip()


def _fallback(extracted_name: str, extracted_address: str, confidence: int = 0) -> dict:
    return {
        "verified_college_name": _clean_name(extracted_name),
        "verified_college_address": clean_address(extracted_address),
        "city": "",
        "resolution_failed": True,
        "match_confidence": confidence,
        "via_cache": False,
    }


def resolve_institution(extracted_name: str, extracted_address: str) -> dict:
    cleaned_ocr_address = clean_address(extracted_address)
    cache = _load_cache()
    # Pass the raw OCR address so the cache lookup can cross-check city.
    cache_key, cached, cache_score = _find_cache_record(
        cache, extracted_name, extracted_address
    )

    if cached:
        logger.info("- Cache hit")
        logger.debug(f"[Resolver] Cache HIT (score={cache_score}) -> {cached['official_name']}")
        return {
            "verified_college_name": cached["official_name"],
            "verified_college_address": cached["official_address"],
            "city": cached["city"],
            "resolution_failed": False,
            "match_confidence": 100,
            "via_cache": True,
        }

    logger.info("- Cache miss")
    logger.debug(f"[Resolver] Cache MISS (best_score={cache_score}). Calling resolver.")

    try:
        data = GeminiResolver(api_key=os.environ["GEMINI_API_KEY"]).resolve(
            extracted_name=extracted_name,
            extracted_address=cleaned_ocr_address,
        )
    except LLMUnverifiableError as exc:
        # The model said it cannot verify — not a hard failure, just flag it.
        logger.debug(f"[Resolver] LLM declined to verify institution: {exc}")
        return _fallback(extracted_name, cleaned_ocr_address)
    except Exception as exc:
        logger.debug(f"[Resolver] Online resolution failed: {exc}")
        return _fallback(extracted_name, cleaned_ocr_address)

    official_name = _clean_name(data.get("verified_college_name", ""))
    official_address = clean_address(data.get("verified_college_address", ""))
    city = _clean_city(data.get("city", ""), official_address or cleaned_ocr_address)
    final_name = _append_city(official_name, city)

    if _is_generic_name(official_name):
        logger.debug(f"[Resolver] Rejecting generic institution name: {official_name!r}")
        return _fallback(extracted_name, cleaned_ocr_address)

    confidence = _compute_confidence(official_name, extracted_name)
    logger.debug(
        f"[Resolver] Match confidence: {confidence} - "
        f"'{official_name}' vs '{extracted_name}'"
    )
    if confidence < CONFIDENCE_REJECT_THRESHOLD:
        logger.debug(
            f"[Resolver] Confidence {confidence} < {CONFIDENCE_REJECT_THRESHOLD}. "
            "Returning fallback."
        )
        return _fallback(extracted_name, cleaned_ocr_address, confidence)

    if not official_address or not city:
        logger.debug("[Resolver] Missing official address or city. Returning fallback.")
        return _fallback(extracted_name, cleaned_ocr_address, confidence)

    canonical_key = _normalise_key(official_name)
    # When looking up the official name to merge cache entries, pass the
    # resolved city as a pseudo-address so city guard can still be applied.
    existing_key, existing_record, _ = _find_cache_record(
        cache, official_name, city
    )
    write_key = existing_key or canonical_key
    aliases = set((existing_record or {}).get("aliases", []))
    aliases.add(_normalise_key(extracted_name))

    cache[write_key] = {
        "official_name": final_name,
        "official_address": official_address,
        "city": city,
        "aliases": sorted(alias for alias in aliases if alias),
    }
    _save_cache(cache)
    logger.debug(f"[Cache] Saved: {write_key!r} (confidence={confidence})")
    logger.debug(f"Verified College: {final_name}")

    return {
        "verified_college_name": final_name,
        "verified_college_address": official_address,
        "city": city,
        "resolution_failed": False,
        "match_confidence": confidence,
        "via_cache": False,
    }

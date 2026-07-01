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
from abc import ABC, abstractmethod

import google.generativeai as genai
from dotenv import load_dotenv
from serpapi import GoogleSearch

load_dotenv()

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

    MODEL_NAME = "gemini-1.5-flash"

    _SYSTEM_PROMPT = """\
You are an institution entity-resolution assistant.

You will receive:
  1. An extracted college name (possibly noisy / misspelled).
  2. An extracted college address (possibly noisy or incomplete).
  3. Up to 5 Google search results (title, snippet, url).

Your job:
  - Rank the search results and determine the most likely real institution.
  - Infer the official institution name, official address, and city.

Rules:
  - Return ONLY strict JSON. No markdown. No explanation. No extra keys.
  - JSON schema:
      {
        "verified_college_name": "<Official institution name>",
        "verified_college_address": "<Full official address>",
        "city": "<City only — not district, not state, not PIN code>"
      }
  - If you cannot determine the institution with reasonable confidence,
    return the extracted values as-is.
"""

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=self.MODEL_NAME,
            system_instruction=self._SYSTEM_PROMPT,
        )

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

    def resolve(
        self,
        extracted_name: str,
        extracted_address: str,
        search_results: list[dict],
    ) -> dict:
        user_message = self._build_user_message(
            extracted_name, extracted_address, search_results
        )

        response = self._model.generate_content(user_message)
        raw_text = response.text.strip()

        # Strip any accidental markdown code fences
        json_match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
        if json_match:
            raw_text = json_match.group(0)

        return json.loads(raw_text)


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

    try:
        # Step 1 — Build and execute search query
        query = f'"{extracted_name}" medical college Maharashtra'
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

    # Step 4 — Append city to the college name (Python-enforced, not Gemini)
    verified_name = llm_result["verified_college_name"].strip()
    city          = llm_result["city"].strip()

    final_name = _append_city(verified_name, city)

    result = {
        "verified_college_name":    final_name,
        "verified_college_address": llm_result["verified_college_address"].strip(),
        "city":                     city,
        "resolution_failed":        False,
    }

    print("[Resolver] Institution resolved.")
    print(f"Verified College: {final_name}")

    return result

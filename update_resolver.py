import os
import re

with open("web_resolver.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Comment out serpapi
content = content.replace(
    "from serpapi import GoogleSearch",
    "# from serpapi import GoogleSearch"
)

# 2. Comment out SearchProvider and SerpApiProvider
search_provider_code = """class SearchProvider(ABC):
    \"\"\"Abstract search interface. Implement this to swap search backends.\"\"\"

    @abstractmethod
    def perform_search(self, query: str) -> list[dict]:
        \"\"\"
        Execute a web search and return up to 5 organic results.

        Each result dict must contain:
            title   : str
            snippet : str
            url     : str
        \"\"\"
        raise NotImplementedError


class SerpApiProvider(SearchProvider):
    \"\"\"
    Concrete search provider backed by SerpAPI (Google Search).

    To replace with Brave / Bing / Tavily:
      1. Create a new subclass of SearchProvider.
      2. Change the one-line wiring in resolve_institution().
    \"\"\"

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

        return results"""

commented_search_provider = "\\n".join(["# " + line for line in search_provider_code.split("\\n")])

content = content.replace(search_provider_code, commented_search_provider)


# 3. Update GeminiClient System Prompt
old_prompt = """    _SYSTEM_PROMPT = \"\"\"\\
You are an institution entity-resolution assistant for Indian medical colleges.

You will receive:
  1. An extracted college name (possibly noisy / misspelled).
  2. An extracted college address (for context only — do NOT copy it into output).
  3. Up to 5 numbered Google search results, each with a title, snippet, and URL.

Your job:
  - Identify which search result most closely matches the extracted institution.
  - You MUST select ONE of the provided search results. Do NOT invent names or
    information that does not appear in the search results.
  - Copy the exact title text from the winning result into the output.
  - Extract the city name from the winning result's title or snippet.

Critical rules:
  - The address field in the output is NOT required.  Do NOT extract an address
    from any Google snippet.  Snippets frequently contain ad copy, phone numbers,
    and website descriptions that are not valid postal addresses.
  - Return ONLY strict JSON. No markdown. No explanation. No extra keys.
  - JSON schema:
      {
        "winning_title": "<Exact title string from the best matching result>",
        "city": "<City only — not district, not state, not PIN code>"
      }
  - If none of the results match with reasonable confidence, copy the extracted
    name verbatim as winning_title and leave city as an empty string.
\"\"\""""

new_prompt = """    _SYSTEM_PROMPT = \"\"\"\\
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
\"\"\""""

content = content.replace(old_prompt, new_prompt)


# 4. Update GEMINI_MODELS
old_models = """    GEMINI_MODELS = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]"""

new_models = """    GEMINI_MODELS = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-3-flash-preview",
    ]"""

content = content.replace(old_models, new_models)


# 5. Update _build_user_message
old_build_message = """    def _build_user_message(
        self,
        extracted_name: str,
        extracted_address: str,
        search_results: list[dict],
    ) -> str:
        lines = [
            f"Extracted college name: {extracted_name}",
            f"Extracted college address (context only): {extracted_address or '(not available)'}",
            "",
            "Search results:",
        ]
        for i, r in enumerate(search_results, 1):
            lines.append(f"  [{i}] Title:   {r['title']}")
            lines.append(f"       Snippet: {r['snippet']}")
            lines.append(f"       URL:     {r['url']}")
            lines.append("")

        return "\\n".join(lines)"""

new_build_message = """    def _build_user_message(
        self,
        extracted_name: str,
        extracted_address: str,
    ) -> str:
        lines = [
            f"Extracted college name: {extracted_name}",
            f"Extracted college address: {extracted_address or '(not available)'}",
            ""
        ]
        return "\\n".join(lines)"""

content = content.replace(old_build_message, new_build_message)


# 6. Update LLMClient signature
old_llm_resolve = """    def resolve(
        self,
        extracted_name: str,
        extracted_address: str,
        search_results: list[dict],
    ) -> dict:"""

new_llm_resolve = """    def resolve(
        self,
        extracted_name: str,
        extracted_address: str,
    ) -> dict:"""

content = content.replace(old_llm_resolve, new_llm_resolve)


# 7. Update GeminiClient resolve body
old_resolve_body = """        user_message = self._build_user_message(
            extracted_name, extracted_address, search_results
        )"""

new_resolve_body = """        user_message = self._build_user_message(
            extracted_name, extracted_address
        )"""

content = content.replace(old_resolve_body, new_resolve_body)

# 8. Update GeminiClient SDK config
old_config = """                    config=types.GenerateContentConfig(
                        system_instruction=self._SYSTEM_PROMPT,
                        temperature=0.0,
                        response_mime_type="application/json",
                        response_schema={
                            "type": "object",
                            "properties": {
                                "winning_title": {"type": "string"},
                                "city":          {"type": "string"},
                            },
                            "required": ["winning_title", "city"],
                        },
                    ),"""

new_config = """                    config=types.GenerateContentConfig(
                        system_instruction=self._SYSTEM_PROMPT,
                        temperature=0.0,
                        tools=[{"google_search": {}}],
                    ),"""

content = content.replace(old_config, new_config)


# 9. Update _parse_json_response
old_parse = """    def _parse_json_response(self, raw_text: str, extracted_name: str) -> dict:
        gemini_data = json.loads(raw_text)
        winning_title = gemini_data.get("winning_title", extracted_name)
        city          = gemini_data.get("city", "")

        # Strip common search-result title noise (" - Wikipedia", " | Official Site")
        clean_name = self._TITLE_NOISE.sub("", winning_title).strip()

        return {
            "verified_college_name": clean_name,
            "city":                  city,
            # verified_college_address is intentionally absent — resolve_institution()
            # fills it from the OCR extraction via clean_address().
        }"""

new_parse = """    def _parse_json_response(self, raw_text: str, extracted_name: str) -> dict:
        gemini_data = json.loads(raw_text)
        verified_name = gemini_data.get("verified_college_name", extracted_name)
        verified_address = gemini_data.get("verified_college_address", "")

        # Strip common search-result title noise (" - Wikipedia", " | Official Site")
        clean_name = self._TITLE_NOISE.sub("", verified_name).strip()

        return {
            "verified_college_name": clean_name,
            "verified_college_address": verified_address,
        }"""

content = content.replace(old_parse, new_parse)


# 10. Update resolve_institution entry point
old_resolve_inst = """    # --- Wire in the concrete providers (single location for future swaps) ---
    search_provider: SearchProvider = SerpApiProvider(
        api_key=os.environ["SERPAPI_API_KEY"]
    )
    llm_client: LLMClient = GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"]
    )
    # -------------------------------------------------------------------------

    # The OCR address is authoritative — clean it once here for all code paths.
    cleaned_ocr_address = clean_address(extracted_address)"""

new_resolve_inst = """    # --- Wire in the concrete providers (single location for future swaps) ---
    # search_provider: SearchProvider = SerpApiProvider(
    #     api_key=os.environ["SERPAPI_API_KEY"]
    # )
    llm_client: LLMClient = GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"]
    )
    # -------------------------------------------------------------------------

    # Fallback address in case Gemini fails
    cleaned_ocr_address = clean_address(extracted_address)"""

content = content.replace(old_resolve_inst, new_resolve_inst)


# 11. Remove search steps in resolve_institution
old_search_steps = """    # -----------------------------------------------------------------------
    # Step 1 — Build query list and execute with progressive relaxation
    # -----------------------------------------------------------------------
    queries = _build_queries(extracted_name, extracted_address)
    search_results: list[dict] = []

    try:
        for attempt, query in enumerate(queries, 1):
            print(f"[Resolver] Search attempt {attempt}/{len(queries)}: {query!r}")
            results = search_provider.perform_search(query)
            if results:
                search_results = results
                print(f"[Resolver] Retrieved {len(search_results)} result(s) on attempt {attempt}.")
                break
            print(f"[Resolver] No results for attempt {attempt}. Relaxing query...")

        if not search_results:
            print("[Resolver] All query tiers exhausted with zero results. Using extracted values.")
            return fallback

    except Exception as exc:
        print(f"[Resolver] Search failed: {exc}")
        print("[Resolver] Online verification unavailable. Using extracted values.")
        return fallback

    # -----------------------------------------------------------------------
    # Step 2 — Ask the LLM to identify the institution from search results
    # -----------------------------------------------------------------------
    try:
        print("[Resolver] Sending candidates to Gemini...")
        llm_result = llm_client.resolve(extracted_name, extracted_address, search_results)"""

new_search_steps = """    # -----------------------------------------------------------------------
    # Step 1 & 2 — Ask the LLM to directly search and identify the institution
    # -----------------------------------------------------------------------
    try:
        print("[Resolver] Sending candidates to Gemini with Native Search Grounding...")
        llm_result = llm_client.resolve(extracted_name, extracted_address)"""

content = content.replace(old_search_steps, new_search_steps)


# 12. Finalize resolve_institution assembly
old_assembly = """    # -----------------------------------------------------------------------
    # Step 4 — Compute entity resolution confidence
    # -----------------------------------------------------------------------
    verified_name = llm_result["verified_college_name"].strip()
    city          = llm_result.get("city", "").strip()

    match_confidence = _compute_confidence(verified_name, extracted_name)
    label            = _confidence_label(match_confidence)
    print(f"[Resolver] Match confidence: {match_confidence} ({label}) — "
          f"'{verified_name}' vs '{extracted_name}'")

    # Reject low-confidence matches to avoid polluting output with bad candidates
    if match_confidence < _CONFIDENCE_REJECT_THRESHOLD:
        print(
            f"[Resolver] Confidence {match_confidence} < {_CONFIDENCE_REJECT_THRESHOLD} "
            "(Reject threshold). Returning fallback."
        )
        return {**fallback, "match_confidence": match_confidence}

    # -----------------------------------------------------------------------
    # Step 5 — Assemble final result
    # -----------------------------------------------------------------------
    final_name    = _append_city(verified_name, city)
    final_address = cleaned_ocr_address   # OCR address is authoritative

    result = {
        "verified_college_name":    final_name,
        "verified_college_address": final_address,
        "city":                     city,
        "resolution_failed":        False,
        "match_confidence":         match_confidence,
    }"""

new_assembly = """    # -----------------------------------------------------------------------
    # Step 4 — Compute entity resolution confidence
    # -----------------------------------------------------------------------
    verified_name = llm_result.get("verified_college_name", "").strip()
    verified_address = llm_result.get("verified_college_address", "").strip()

    match_confidence = _compute_confidence(verified_name, extracted_name)
    label            = _confidence_label(match_confidence)
    print(f"[Resolver] Match confidence: {match_confidence} ({label}) — "
          f"'{verified_name}' vs '{extracted_name}'")

    # Reject low-confidence matches to avoid polluting output with bad candidates
    if match_confidence < _CONFIDENCE_REJECT_THRESHOLD:
        print(
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
    }"""

content = content.replace(old_assembly, new_assembly)


with open("web_resolver.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done")

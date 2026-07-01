import json
import ollama
import re

MODEL = "qwen2.5:7b-instruct"

SYSTEM_PROMPT = """
You are an expert document extraction system.

You are given OCR text extracted from a scholarship application document.

The page may be one of:
1. Bonafide Certificate
2. Student Identity Card
3. Some completely unrelated document (Aadhaar, Ration Card, Self Declaration, etc.)

Your task:

If the page is NOT a Bonafide Certificate or Student Identity Card, return exactly:

{
  "relevant": false
}

If it IS relevant, return ONLY valid JSON in this format:

{
  "relevant": true,
  "document_type": "bonafide",
  "student_name": "...",
  "academic_year": "...",
  "college_name": "...",
  "college_address": "...",
}

or

{
  "relevant": true,
  "document_type": "student_id",
  "student_name": "...",
  "academic_year": "...",
  "college_name": "...",
  "college_address": "...",
}

--- FIELD DEFINITIONS ---

FIELD 1 — college_name

This should contain the official institution name followed ONLY by the locality or city
if it forms part of the institution's commonly used identity.

Good examples:
  "Takhatmal Shrivallabh Homoeopathic Medical College & Hospital, Rajapeth, Amravati"
  "Gondia Homoeopathic Medical College & Hospital, Surya Tola, Gondia"

Rules for college_name:
  - Do NOT include PIN codes.
  - Do NOT include district names unless they are part of the institution's official name.
  - Do NOT include state names.
  - Do NOT include building names.
  - Do NOT include campus-only addresses unless commonly used to identify the institution.
  - If the college name is genuinely missing, use null.

FIELD 2 — college_address

This should contain the COMPLETE postal address exactly as it appears in the document.

Include everything available:
  Campus name, road, area, PIN code, district, state.

Good examples:
  "HOMOEO SADAN, RAJAPETH, AMRAVATI-444606"
  "GHMC CAMPUS, SURYA TOLA, GONDIA-441614, DISTRICT GONDIA, MAHARASHTRA"

Rules for college_address:
  - Preserve punctuation wherever possible.
  - If the address is genuinely missing, use null.



--- OCR CORRECTION RULES ---

Never invent missing information.

However, you SHOULD correct obvious OCR mistakes, including:
  - missing spaces
  - missing commas
  - incorrect capitalisation
  - obvious spelling mistakes
when the intended text is clear from context.

Do NOT guess if multiple interpretations are equally plausible.

--- OUTPUT RULES ---

- Never include markdown.
- Never explain.
- Output JSON only.
"""


def is_satisfactory(result):
    """Return True only when the result contains usable college data."""
    if result is None:
        return False
    if not result.get("relevant"):
        return False
    if not (result.get("college_name") or "").strip():
        return False
    if not (result.get("college_address") or "").strip():
        return False
    return True


def extract_information(ocr_text):

    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": ocr_text
            }
        ]
    )

    content = response["message"]["content"].strip()

    json_match = re.search(r'\{.*?\}', content, re.DOTALL)

    if json_match:
        content = json_match.group(0)

    try:
        return json.loads(content)
    except Exception:
        return {
            "relevant": False,
            "parse_error": True,
            "raw_response": content
        }
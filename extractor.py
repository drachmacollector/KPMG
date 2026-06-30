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
  "confidence": 
}

or

{
  "relevant": true,
  "document_type": "student_id",
  "student_name": "...",
  "academic_year": "...",
  "college_name": "...",
  "college_address": "...",
  "confidence": 
}

Rules:

- Never invent information.
- If college name is missing, use null.
- If address is missing, use null.
- Never include markdown.
- Never explain.
- Output JSON only.
"""


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

# Replace the start/end string slicing with this regex search:
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
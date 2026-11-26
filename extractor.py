import json
import ollama
import re
from logger_config import logger

MODEL = "qwen2.5:7b-instruct"
NUM_CTX = 8192

SYSTEM_PROMPT = """
You are an expert document extraction and OCR correction system.

You are given raw OCR text extracted from a scholarship application document.
The OCR text is noisy — it may contain spelling mistakes, missing spaces, wrong
capitalisation, garbled words, and common character substitutions.

The page may be one of:
1. Bonafide Certificate
2. Student Identity Card
3. Some completely unrelated document (Aadhaar, Ration Card, Self Declaration, etc.)

---

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
  "college_address": "..."
}

or

{
  "relevant": true,
  "document_type": "student_id",
  "student_name": "...",
  "academic_year": "...",
  "college_name": "...",
  "college_address": "..."
}

---

STEP 1 — OCR CORRECTION (do this before extracting anything)

Treat all OCR text as noisy input. Before extracting fields, mentally correct the text.

Always correct these types of errors:

MISSING SPACES
  MedicalCollege         → Medical College
  HospitalAmravati       → Hospital Amravati
  ShikshanSanstha        → Shikshan Sanstha

WRONG CAPITALISATION (OCR all-caps artefacts)
  SHR                    → Shri
  SHRI                   → Shri
  DR.                    → Dr.
  SMT.                   → Smt.
  Output should always be Title Case for proper nouns

COMMON SPELLING CORRUPTIONS (apply when the intended word is obvious)
  Shkshan / Shkhsan      → Shikshan
  Hospita / Hospita1     → Hospital
  Maharaj / Mahraj       → Maharaj
  Sanstha / Sanshtha     → Sanstha
  Ayurvedick             → Ayurvedic
  Medica1                → Medical
  Co11ege / Cottege      → College
  HOMOEOPATHIC           → HOMEOPATHIC
  ARALBIHARI             → ATALBIHARI

COMMON CHARACTER SUBSTITUTIONS
  0 confused for O       → use O in names/words, 0 in numbers
  1 confused for I or l  → use I/l in names/words
  rn confused for m      → e.g. "Ayurvedic" not "Ayurvedic"
  cl confused for d      → correct to the obvious word

DO NOT GUESS. Only correct when the intended word is unambiguous from context.
If two interpretations are equally plausible, preserve the OCR text as-is.

---

STEP 2 — SEPARATE MANAGING ORGANISATION FROM COLLEGE NAME

Some certificates print a managing trust, educational society, or charitable trust
ABOVE or BELOW the actual college name. These are two separate entities.

Phrases that identify the MANAGING ORGANISATION (not the college):
  "Managed by"
  "Operated by"
  "Sanchalit"
  "Under the aegis of"
  "Educational Society"
  "Charitable Trust"
  "Trust"
  "Late Shri ..."
  "Foundation"

The MANAGING ORGANISATION must NEVER be included in college_name.

Examples:

  OCR text:
    Narsingh K. Dube Charitable Trust
    Nallasopara Ayurvedic Medical College

  college_name = "Nallasopara Ayurvedic Medical College"   ← correct
  college_name = "Narsingh K. Dube Charitable Trust Nallasopara Ayurvedic Medical College"  ← WRONG

  OCR text:
    Chhatrapati Shahu Maharaj Shikshan Sanstha
    Government Medical College

  college_name = "Government Medical College"   ← correct

  OCR text:
    Late Shri Educational Society's
    Gondia Homoeopathic Medical College & Hospital

  college_name = "Gondia Homoeopathic Medical College & Hospital"  ← correct

The college_name must contain ONLY the degree-granting institution name.

---

FIELD DEFINITIONS

FIELD 1 — college_name

The official name of the degree-granting institution.
Include only the locality or city if it is genuinely part of the institution's name.

Good examples:
  "Takhatmal Shrivallabh Homoeopathic Medical College & Hospital, Rajapeth, Amravati"
  "Gondia Homoeopathic Medical College & Hospital, Surya Tola, Gondia"

Rules for college_name:
  - Do NOT include PIN codes.
  - Do NOT include district names unless part of the institution's official name.
  - Do NOT include state names.
  - Do NOT include building names.
  - Do NOT include managing trust / educational society names.
  - If the college name is genuinely missing, use null.

FIELD 2 — college_address

The COMPLETE postal address exactly as it appears in the document (after OCR correction).

Include everything available:
  Campus name, road, area, PIN code, district, state.

Good examples:
  "HOMOEO SADAN, RAJAPETH, AMRAVATI-444606"
  "GHMC CAMPUS, SURYA TOLA, GONDIA-441614, DISTRICT GONDIA, MAHARASHTRA"

Rules for college_address:
  - Preserve punctuation wherever possible.
  - If the address is genuinely missing, use null.
  - Trust names, educational societies, foundations, or charitable organisations
    must NEVER populate the college_address field unless genuine postal address
    information (road, area, PIN code, city) immediately follows them in the
    source text.
  - If the only text available after the college name is a trust or foundation
    name (e.g. "Late Kakasaheb Mhaske Memorial Medical Foundation's"), return
    college_address: null.

Examples of what NOT to do:
  OCR text:
    Shri Vivekananda Education Society's
    Nanded Medical College

  college_address = "Shri Vivekananda Education Society's"  ← WRONG
  college_address = null                                     ← CORRECT (no postal info)

  OCR text:
    Late Kakasaheb Mhaske Memorial Medical Foundation's
    Latur Road, Nanded-431601

  college_address = "Latur Road, Nanded-431601"             ← CORRECT (postal info follows)

---

OUTPUT RULES

- Never include markdown.
- Never explain your reasoning.
- Output JSON only.
- Do not add any fields beyond the schema above.
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
    """
    Send OCR text to the LLM for correction + structured extraction.

    Parameters
    ----------
    ocr_text : str
        Raw OCR text (the 'text' field from ocr_engine.ocr_image()).

    Returns
    -------
    dict
        Parsed JSON from the LLM.  On parse failure, returns
        {"relevant": False, "parse_error": True, "raw_response": "..."}.
    """
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
        ],
        # format="json" constrains decoding to valid JSON.  num_ctx is raised
        # explicitly because the system prompt alone is ~2k tokens; older
        # Ollama defaults (2048) would silently truncate the prompt + OCR text.
        format="json",
        options={"temperature": 0.0, "num_ctx": NUM_CTX},
    )

    content = response["message"]["content"].strip()
    logger.debug(f"[Extractor] Raw LLM response: {content}")
    return parse_llm_json(content)


def parse_llm_json(content):
    """Parse the model's reply into a dict, tolerating stray text or fences."""
    content = (content or "").strip()
    candidates = [content]
    # Fallback: first {...} block (handles markdown fences / leading prose).
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        candidates.append(json_match.group(0))
    json_match = re.search(r'\{.*?\}', content, re.DOTALL)
    if json_match:
        candidates.append(json_match.group(0))

    last_error = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
            last_error = ValueError("LLM response is not a JSON object")
        except Exception as e:
            last_error = e

    logger.error(f"[Extractor] JSON parsing failed: {last_error}")
    return {
        "relevant": False,
        "parse_error": True,
        "raw_response": content
    }


def check_ollama_ready():
    """
    Preflight: confirm the Ollama server is reachable and MODEL is pulled.
    Returns (ok: bool, message: str).
    """
    try:
        listing = ollama.list()
    except Exception as e:
        return False, (
            f"Cannot reach the Ollama server ({e}). Make sure Ollama is installed "
            "and running."
        )
    models = listing.get("models", []) if isinstance(listing, dict) else getattr(listing, "models", [])
    names = set()
    for m in models or []:
        name = m.get("model") or m.get("name") if isinstance(m, dict) else (getattr(m, "model", None) or getattr(m, "name", None))
        if name:
            names.add(name)
    if MODEL not in names and f"{MODEL}:latest" not in names:
        return False, (
            f"The Ollama model '{MODEL}' is not installed. Run: ollama pull {MODEL}"
        )
    return True, "ok"

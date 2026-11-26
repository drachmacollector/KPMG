"""
Accuracy scoring for a processed claim (pure functions, no heavy imports).

Kept separate from verify_colleges.py so it can be unit-tested without
starting PaddleOCR, Ollama or Playwright.
"""
from __future__ import annotations

from rapidfuzz import fuzz

# Two documents "agree" when their extracted college names score at least
# this on rapidfuzz token_set_ratio.
NAME_AGREEMENT_THRESHOLD = 85


def _relevant_documents(ocr_metrics_list):
    """Map document id -> extracted college name for relevant pages."""
    docs = {}
    for m in ocr_metrics_list:
        if not m.get("is_relevant") or m.get("line_count", 0) <= 0:
            continue
        doc_id = m.get("document") or m.get("page") or f"page{len(docs)}"
        name = (m.get("college_name") or "").strip()
        # Keep the first non-empty name seen for each document.
        if doc_id not in docs or (not docs[doc_id] and name):
            docs[doc_id] = name
    return docs


def compute_accuracy(ocr_metrics_list, resolved=None):
    """
    Compute a programmatic accuracy score (0-100) from objective signals.

    Parameters
    ----------
    ocr_metrics_list : list[dict]
        One dict per processed page with keys avg_confidence, line_count,
        is_relevant (bool), and optionally document (str, source document id)
        and college_name (str, LLM-extracted name for that page).
    resolved : dict | None
        Output of resolve_institution().

    Scoring breakdown (100 points total):
      OCR confidence                  (30 pts max)
        mean avg_confidence of RELEVANT pages * 30 (falls back to all pages
        with text when no page was relevant)

      Web verification confidence     (40 pts max)
        round((match_confidence/100) * 40) when resolution succeeded, else 0
        (cache hits carry match_confidence=100 -> full 40 pts)

      Cross-document agreement        (30 pts max)
        >= 2 distinct relevant documents whose extracted college names agree
           (token_set_ratio >= NAME_AGREEMENT_THRESHOLD)          -> 30 pts
        exactly 1 relevant document, or >= 2 that do not agree      -> 15 / 0 pts
           (1 document -> 15 pts; disagreeing documents -> 0 pts, because
            conflicting certificates are a red flag for an audit)
        no relevant documents                                       ->  0 pts
        Pages of the same document count once (a 2-page bonafide is one
        document).  Aadhaar, ration card and self declarations are never
        relevant.
    """
    ocr_metrics_list = ocr_metrics_list or []

    # --- Component 1: OCR confidence (30 pts) ---
    relevant_pages = [m for m in ocr_metrics_list if m.get("is_relevant") and m.get("line_count", 0) > 0]
    scored_pages = relevant_pages or [m for m in ocr_metrics_list if m.get("line_count", 0) > 0]
    if scored_pages:
        avg_conf = sum(m.get("avg_confidence", 0.0) for m in scored_pages) / len(scored_pages)
    else:
        avg_conf = 0.0
    ocr_score = min(round(avg_conf * 30), 30)

    # --- Component 2: Graduated web verification score (40 pts) ---
    if resolved is not None and not resolved.get("resolution_failed", True):
        match_confidence = resolved.get("match_confidence", 0) or 0
        verification_score = round((match_confidence / 100) * 40)
    else:
        verification_score = 0

    # --- Component 3: Cross-document agreement (30 pts) ---
    docs = _relevant_documents(ocr_metrics_list)
    if len(docs) >= 2:
        names = [n.lower() for n in docs.values() if n]
        if len(names) < 2:
            # Only one document produced a name: nothing to compare against.
            return min(ocr_score + verification_score + 15, 100)
        agree = False
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if fuzz.token_set_ratio(names[i], names[j]) >= NAME_AGREEMENT_THRESHOLD:
                    agree = True
                    break
            if agree:
                break
        cross_doc_score = 30 if agree else 0
    elif len(docs) == 1:
        cross_doc_score = 15
    else:
        cross_doc_score = 0

    return min(ocr_score + verification_score + cross_doc_score, 100)

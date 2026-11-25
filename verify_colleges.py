import os

# Force protobuf pure-Python implementation so that PaddlePaddle's older
# protobuf requirement and google-genai's newer requirement don't collide at
# the C++ extension layer.  Must be set before ANY module imports protobuf.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import socket

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm

from logger_config import emit_event, logger
from scoring import compute_accuracy

load_dotenv()

# Rows with accuracy below this threshold are flagged for manual review.
ACCURACY_THRESHOLD = 80

# Values written to the `online_verification_status` column.
STATUS_VERIFIED = "VERIFIED"   # web resolution succeeded
STATUS_FAILED = "FAILED"       # documents read, but web resolution failed
STATUS_NO_DOCS = "NO_DOCS"     # no relevant document could be extracted
STATUS_ERROR = "ERROR"         # portal / processing error — always retried
TERMINAL_STATUSES = {STATUS_VERIFIED, STATUS_FAILED, STATUS_NO_DOCS}

ACK_COLUMN = "acknowledgement_no"

DOWNLOAD_TIMEOUT_SECS = 60
GRID_WAIT_SECS = 20

OUTPUT_COLUMNS = [
    'corrected_college_name',
    'corrected_college_address',
    'accuracy',
    'manual_review',
    'online_verification_status'
]

# ---------------------------------------------------------------------------
# Priority / fallback document groups
# ---------------------------------------------------------------------------
PRIORITY_DOCS = ["bonafide", "college_id"]

FALLBACK_DOCS = [
    "aadhaar",
    "ration",
    "self_declaration",
    "education_self_declaration",
]

_TTY = sys.stdout.isatty()


def _env_flag(name, default="false"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Excel I/O
# ---------------------------------------------------------------------------

def normalize_ack(value):
    """Return the acknowledgement number as a clean string ('' if missing)."""
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    if text.lower() in ("nan", "none"):
        return ""
    # Integers that went through a float column come back as "12345.0".
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text


def load_sheet(path, sheet_name):
    """Read one sheet, keeping the acknowledgement column as text."""
    with pd.ExcelFile(path) as xls:
        logger.debug(f"Sheets found in {path}: {xls.sheet_names}")
        if sheet_name not in xls.sheet_names:
            raise SystemExit(
                f"Sheet '{sheet_name}' was not found in {os.path.basename(path)}. "
                f"Available sheets: {', '.join(xls.sheet_names)}"
            )
        header = xls.parse(sheet_name, nrows=0)
        dtype = {c: str for c in header.columns if str(c).strip() == ACK_COLUMN}
        df = xls.parse(sheet_name, dtype=dtype)

    df.columns = df.columns.str.strip()
    if ACK_COLUMN not in df.columns:
        raise SystemExit(f"Column '{ACK_COLUMN}' was not found in sheet '{sheet_name}'.")

    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        # Explicitly enforce string dtype to prevent float64 rejection on empty columns
        df[col] = df[col].fillna("").astype(str)
    return df


def save_with_retry(df, filename, sheet_name):
    """
    Atomically write the sheet: write a temp file, then os.replace() it over
    the output.  A forced stop or crash mid-write can therefore never leave a
    truncated/corrupt output workbook behind.
    """
    root, _ = os.path.splitext(filename)
    tmp_path = f"{root}.saving.xlsx"
    while True:
        try:
            df.to_excel(tmp_path, sheet_name=sheet_name, index=False)
            os.replace(tmp_path, filename)
            logger.info("[OK] Progress Saved\n")
            return
        except PermissionError:
            logger.info("- Output Excel file is currently open. Close it — retrying in 5s...")
            time.sleep(5)


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def download_document(url, save_path):
    retries = 3
    delays = [2, 4]  # Wait 2s, then 4s on failures.

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SECS) as resp, open(save_path, "wb") as out:
                shutil.copyfileobj(resp, out)
            logger.debug(f"Downloaded: {save_path}")
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, TimeoutError, ConnectionError) as e:
            if attempt < len(delays):
                wait_time = delays[attempt]
                logger.debug(f"- Retry {attempt + 1}/{len(delays)} for {os.path.basename(save_path)} in {wait_time}s ({e})")
                time.sleep(wait_time)
            else:
                logger.error(f"Download failed after retries: {e}")
        except Exception as e:
            logger.error(f"Download failed unexpectedly: {e}")
            break

    return False


def _url_extension(url):
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext if re.fullmatch(r"\.[a-z0-9]{2,5}", ext or "") else ""


def download_and_normalize(doc_subset, documents, claim_folder, pages_folder, processed_hashes):
    """Download `doc_subset` keys from `documents`, normalize, return page list."""
    from document_processor import calculate_sha256, normalize_document, sniff_extension

    new_pages = []
    skipped = []
    downloaded_count = 0

    for doc_type in doc_subset:
        url = documents.get(doc_type)
        if not url:
            skipped.append(doc_type.replace('_', ' ').title())
            continue

        logger.debug(f"[*] Downloading {doc_type.replace('_', ' ').title()}...")
        tmp_path = os.path.join(claim_folder, f"{doc_type}.download")

        if not download_document(url, tmp_path):
            continue

        # Name the file by its real type (portal URLs don't always carry one).
        extension = sniff_extension(tmp_path) or _url_extension(url) or ".bin"
        filename = f"{doc_type}{extension}"
        output_path = os.path.join(claim_folder, filename)
        os.replace(tmp_path, output_path)

        logger.info(f"[OK] {doc_type.replace('_', ' ').title()} downloaded")

        file_hash = calculate_sha256(output_path)
        if file_hash in processed_hashes:
            logger.debug(f"Duplicate skipped: {filename}")
            continue

        processed_hashes[file_hash] = filename
        downloaded_count += 1

        pages = normalize_document(output_path, pages_folder, doc_type)
        new_pages.extend(pages)
        logger.debug(f"{filename} -> {len(pages)} page(s)")

    for skip_doc in skipped:
        logger.info(f"- {skip_doc} not uploaded")
    if downloaded_count > 0:
        logger.debug(f"[*] Downloaded {downloaded_count}/{len(doc_subset)} documents")

    return new_pages


# ---------------------------------------------------------------------------
# OCR + extraction
# ---------------------------------------------------------------------------

def _document_of(page_path):
    """'.../bonafide_page001.png' -> 'bonafide'."""
    base = os.path.splitext(os.path.basename(page_path))[0]
    return base.rsplit("_page", 1)[0]


def ocr_and_extract(page_paths):
    """
    OCR each page and run LLM extraction.

    Returns
    -------
    tuple(dict | None, list[dict])
        (best_result, all_ocr_metrics)
        best_result      — best LLM result (bonafide preferred over student_id)
        all_ocr_metrics  — list of per-page OCR metric dicts for accuracy
                           scoring, including 'document', 'is_relevant' and
                           'college_name'.
    """
    from extractor import extract_information
    from ocr_engine import ocr_image

    bonafide_result = None
    student_id_result = None
    all_ocr_metrics = []

    logger.info("\nRunning OCR...")

    for page in page_paths:
        logger.debug(f"OCR -> {page}")

        ocr_result = ocr_image(page)

        page_metrics = {
            "document":        _document_of(page),
            "avg_confidence":  ocr_result["avg_confidence"],
            "min_confidence":  ocr_result["min_confidence"],
            "high_conf_ratio": ocr_result["high_conf_ratio"],
            "line_count":      ocr_result["line_count"],
            "is_relevant":     False,   # default; updated if LLM confirms relevance
            "college_name":    "",
        }
        all_ocr_metrics.append(page_metrics)

        ocr_text = ocr_result["text"]

        if not ocr_text.strip():
            logger.debug(f"No text detected on {page}.")
            continue

        logger.debug(
            f"OCR metrics — avg_conf={ocr_result['avg_confidence']:.2%}  "
            f"min_conf={ocr_result['min_confidence']:.2%}  "
            f"high_ratio={ocr_result['high_conf_ratio']:.2%}  "
            f"lines={ocr_result['line_count']}"
        )

        try:
            result = extract_information(ocr_text)
        except Exception as e:
            logger.error(f"LLM failed on {page}: {e}")
            continue

        logger.debug(f"{result}")

        if not result.get("relevant"):
            continue

        page_metrics["is_relevant"] = True
        page_metrics["college_name"] = (result.get("college_name") or "").strip()
        doc_type_display = str(result.get("document_type", "document")).replace('_', ' ').title()
        logger.info(f"[OK] Relevant document: {doc_type_display}")

        if result.get("document_type") == "bonafide":
            if bonafide_result is None:
                bonafide_result = result
        elif result.get("document_type") == "student_id":
            if student_id_result is None:
                student_id_result = result

    best_result = bonafide_result or student_id_result

    if best_result:
        logger.debug("College extracted successfully.")
    else:
        logger.info("- No relevant document found")

    return best_result, all_ocr_metrics


def write_result(df, index, best_result, ocr_metrics):
    """
    Write extraction result and accuracy score into the dataframe row.
    Returns a summary dict for the GUI event stream.
    """
    from web_resolver import resolve_institution

    resolved = None
    status = STATUS_NO_DOCS

    if best_result and best_result.get("relevant"):
        college_name    = (best_result.get("college_name")    or "").strip()
        college_address = (best_result.get("college_address") or "").strip()

        try:
            logger.info(f"\nOCR/Qwen Extracted Name: {college_name}")
            logger.info("\nVerifying College via LLM Search...")
            emit_event("claim_step", step="verifying")
            resolved = resolve_institution(
                extracted_name=college_name,
                extracted_address=college_address,
            )
        except Exception as e:
            logger.error(f"Online verification completely failed: {e}")
            resolved = {
                "verified_college_name": college_name,
                "verified_college_address": college_address,
                "city": "",
                "resolution_failed": True,
                "match_confidence": 0,
                "via_cache": False,
            }

        verified_name = resolved.get("verified_college_name") or ""
        verified_address = resolved.get("verified_college_address") or ""

        df.loc[index, "corrected_college_name"]    = verified_name.upper()
        df.loc[index, "corrected_college_address"] = verified_address.upper()
        status = STATUS_FAILED if resolved.get("resolution_failed") else STATUS_VERIFIED

    df.loc[index, "online_verification_status"] = status

    accuracy = compute_accuracy(ocr_metrics, best_result, resolved)
    df.loc[index, "accuracy"] = f"{accuracy}%"

    # Flag for manual review when accuracy is below the threshold
    # OR when no usable result was obtained at all.
    needs_review = (accuracy < ACCURACY_THRESHOLD) or status != STATUS_VERIFIED
    df.loc[index, "manual_review"] = "YES" if needs_review else ""

    if status == STATUS_VERIFIED:
        logger.info("\n[OK] College Verified")
        logger.info(df.loc[index, "corrected_college_name"])
        if df.loc[index, "corrected_college_address"]:
            logger.info(df.loc[index, "corrected_college_address"])
    else:
        logger.info("\n[FAILED] Resolution Failed\n" if status == STATUS_FAILED else "\n[FAILED] No usable document\n")
    logger.info(f"\nAccuracy: {accuracy}%")
    logger.info(f"Manual Review: {'Yes' if needs_review else 'No'}\n")

    return {
        "status": status,
        "accuracy": accuracy,
        "manual_review": needs_review,
        "college": df.loc[index, "corrected_college_name"],
        "via_cache": bool(resolved and resolved.get("via_cache")),
    }


# ---------------------------------------------------------------------------
# Portal helpers
# ---------------------------------------------------------------------------

# Collects the text of every rendered ag-grid row, grouping pinned/centre
# containers by row-index, and reports how many rows mention the ack number
# as a whole token.
_GRID_CHECK_JS = """
(ack) => {
  const esc = ack.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
  const re = new RegExp('(^|[^A-Za-z0-9])' + esc + '([^A-Za-z0-9]|$)');
  const byIdx = {};
  document.querySelectorAll('.ag-row').forEach(r => {
    const i = r.getAttribute('row-index') || r.getAttribute('row-id') || Math.random();
    byIdx[i] = (byIdx[i] || '') + ' ' + (r.innerText || '');
  });
  const texts = Object.values(byIdx);
  return { count: texts.length, matching: texts.filter(t => re.test(t)).length };
}
"""


def wait_for_filtered_grid(page, ack_no, timeout_secs=GRID_WAIT_SECS):
    """
    Wait until the claims grid shows ONLY rows for `ack_no`.

    Replaces the old fixed sleep(3): if the grid had not refreshed yet, the
    first "View claim form" belonged to the PREVIOUS claim and its documents
    were written against the wrong acknowledgement number.
    """
    deadline = time.time() + timeout_secs
    last = None
    while time.time() < deadline:
        try:
            last = page.evaluate(_GRID_CHECK_JS, ack_no)
            if last["count"] > 0 and last["matching"] == last["count"]:
                return True
        except Exception as e:
            logger.debug(f"Grid check failed: {e}")
        time.sleep(0.5)
    logger.debug(f"Grid never settled on {ack_no}: {last}")
    return False


def extract_document_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    documents = {}
    for label in soup.find_all("label"):
        text = label.get_text(" ", strip=True).lower()
        a = label.find_next("a", href=True)
        if not a:
            continue
        href = urllib.parse.urljoin(base_url, a["href"])

        if "education self declaration" in text:
            documents["education_self_declaration"] = href
        elif "bonafide certificate" in text:
            documents["bonafide"] = href
        elif "college identity" in text:
            documents["college_id"] = href
        elif "aadhaar card" in text:
            documents["aadhaar"] = href
        elif "ration card" in text:
            documents["ration"] = href
        elif (
            text.startswith("5. self declaration")
            or ("self declaration" in text and "education self declaration" not in text)
        ):
            documents["self_declaration"] = href
    return documents


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight():
    """Fail fast with a clear message instead of silently failing every claim."""
    from extractor import check_ollama_ready

    problems = []
    ok, msg = check_ollama_ready()
    if not ok:
        problems.append(msg)
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        problems.append("GEMINI_API_KEY is not set. Enter your Gemini API key in Settings.")
    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    excel_file = os.environ["MAHABOCW_INPUT_FILE"]
    target_sheet_name = os.environ["MAHABOCW_SHEET_NAME"]
    output_excel_file = os.environ["MAHABOCW_OUTPUT_FILE"]

    process_all = _env_flag("EXCEL_PROCESS_ALL")
    retry_failed = _env_flag("MAHABOCW_RETRY_FAILED")
    delete_downloads = _env_flag("MAHABOCW_DELETE_DOWNLOADS")
    stop_file = os.environ.get("MAHABOCW_STOP_FILE", "").strip()

    start_row_env = os.environ.get("EXCEL_START_ROW")
    end_row_env = os.environ.get("EXCEL_END_ROW")
    start_row = int(start_row_env) if start_row_env else None
    end_row = int(end_row_env) if end_row_env else None

    if os.path.normcase(os.path.abspath(excel_file)) == os.path.normcase(os.path.abspath(output_excel_file)):
        raise SystemExit("The output file must be different from the input file (the input would be overwritten).")
    if not process_all and (start_row is None or end_row is None):
        raise SystemExit("Range mode needs both EXCEL_START_ROW and EXCEL_END_ROW.")

    if stop_file and os.path.exists(stop_file):
        os.remove(stop_file)

    problems = preflight()
    if problems:
        for p in problems:
            logger.error(p)
        emit_event("preflight_failed", problems=problems)
        sys.exit(2)

    logger.debug("[*] Initializing MAHABOCW Verification Engine...")
    source = output_excel_file if os.path.exists(output_excel_file) else excel_file
    logger.debug(f"Reading data from {source} sheet '{target_sheet_name}'...")
    df = load_sheet(source, target_sheet_name)
    logger.debug(f"Columns: {df.columns.tolist()}")

    # Load OCR (slow) only after the cheap checks have passed.
    import ocr_engine  # noqa: F401

    os.makedirs("downloads", exist_ok=True)

    if process_all:
        rows_to_process = df
    else:
        # GUI spinboxes emit 1-indexed spreadsheet row numbers (min=2 = first
        # data row).  pd.read_excel strips the header, so df.iloc[0] maps to
        # spreadsheet row 2.  The end bound is exclusive in iloc, so end_row - 1
        # gives the correct inclusive upper limit.
        rows_to_process = df.iloc[start_row - 2: end_row - 1]

    total = len(rows_to_process)
    summary = {s: 0 for s in (STATUS_VERIFIED, STATUS_FAILED, STATUS_NO_DOCS, STATUS_ERROR)}
    summary.update({"skipped": 0, "manual_review": 0, "cache_hits": 0, "processed": 0})
    stopped = False

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False)
        except Exception as e:
            msg = f"Could not start the Chromium browser: {e}"
            logger.error(msg)
            emit_event("preflight_failed", problems=[msg])
            sys.exit(2)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        page.goto("https://iwbms.mahabocw.in/sso", wait_until="domcontentloaded", timeout=60000)

        # --- THE HUMAN HANDOFF ---
        logger.info("\n------------------------------------------------------------\n")
        logger.info("Human Setup Required")
        logger.info("- Preferably don't maximize or resize the window")
        logger.info("- Log in manually")
        logger.info("- Click on the 'Claims' section")
        logger.info("- Drag the 'Acknowledgement Number' column into view")
        logger.info("- Click the 3 bars on the column, click the funnel, and leave the text box open\n")

        emit_event("awaiting_login")
        input("Press ENTER here in the terminal when you are ready to start the loop...")
        logger.debug("Starting automated extraction...")
        emit_event("run_start", total=total)

        with tqdm(total=total, desc="Overall Progress", bar_format="{l_bar}{bar:20}| {n_fmt}/{total_fmt}",
                  colour="green", disable=not _TTY) as main_pbar:
            for n, (index, row) in enumerate(rows_to_process.iterrows(), start=1):
                if stop_file and os.path.exists(stop_file):
                    logger.info("\nStop requested — finishing cleanly.")
                    stopped = True
                    break

                ack_no = normalize_ack(row[ACK_COLUMN])
                status_now = str(row.get("online_verification_status", "")).strip().upper()
                has_name = bool(str(row["corrected_college_name"]).strip())

                skip_reason = None
                if not ack_no:
                    skip_reason = "missing acknowledgement number"
                elif status_now in TERMINAL_STATUSES or (has_name and status_now != STATUS_ERROR):
                    if not (retry_failed and status_now in (STATUS_FAILED, STATUS_NO_DOCS)):
                        skip_reason = "already processed"

                if skip_reason:
                    logger.debug(f"Row {ack_no or index}: {skip_reason}, skipping.")
                    summary["skipped"] += 1
                    emit_event("claim_skipped", n=n, total=total, ack=ack_no, reason=skip_reason)
                    main_pbar.update(1)
                    continue

                logger.info("\n------------------------------------------------------------\n")
                logger.info("Claim")
                logger.info(f"Acknowledgement: {ack_no}\n")
                emit_event("claim_start", n=n, total=total, ack=ack_no)

                claim_folder = os.path.join("downloads", ack_no)
                os.makedirs(claim_folder, exist_ok=True)
                new_page = None
                result_info = None

                try:
                    # --- FILTER MENU HANDLING ---
                    emit_event("claim_step", step="finding claim")
                    filter_box = page.locator('input[type="text"]:visible').first
                    if filter_box.count() == 0 or not filter_box.is_visible():
                        ack_header = page.locator('.ag-header-cell', has_text=re.compile(r"acknowledgement", re.IGNORECASE)).first
                        ack_header.hover()
                        ack_header.locator('.ag-icon-menu').first.click()
                        time.sleep(1)

                    filter_box.fill(ack_no)
                    page.locator('button').filter(has_text="Apply").first.click()
                    logger.debug("Filtering through claims...")

                    if not wait_for_filtered_grid(page, ack_no):
                        raise RuntimeError(f"Claims grid did not show acknowledgement {ack_no} (not found, or the filter did not apply)")

                    # --- NEW TAB HANDLING ---
                    with context.expect_page() as new_page_info:
                        page.locator('a, button').filter(has_text="View claim form").first.click()
                    new_page = new_page_info.value

                    logger.debug("Claim form opened")
                    new_page.wait_for_selector("label", timeout=20000)
                    time.sleep(1)

                    html = new_page.content()
                    if ack_no not in html:
                        logger.warning(f"Acknowledgement {ack_no} not visible on the claim form; relying on the filtered grid match.")
                    documents = extract_document_links(html, new_page.url)

                    logger.info("Documents Found")
                    for doc_key in documents:
                        logger.info(f"[OK] {doc_key.replace('_', ' ').title()}")
                    logger.info("\nDownloading Documents...")

                    pages_folder = os.path.join(claim_folder, "pages")
                    os.makedirs(pages_folder, exist_ok=True)
                    processed_hashes = {}
                    all_ocr_metrics = []

                    # PHASE 1 — Fast path: Bonafide + College ID only
                    emit_event("claim_step", step="downloading")
                    logger.debug("[Phase 1] Trying priority documents (Bonafide + College ID)...")
                    try:
                        phase1_pages = download_and_normalize(PRIORITY_DOCS, documents, claim_folder, pages_folder, processed_hashes)
                    except Exception as e:
                        logger.error(f"Phase 1 document processing failed: {e}")
                        phase1_pages = []

                    from extractor import is_satisfactory
                    best_result = None
                    if phase1_pages:
                        emit_event("claim_step", step="reading documents")
                        try:
                            best_result, phase1_metrics = ocr_and_extract(phase1_pages)
                            all_ocr_metrics.extend(phase1_metrics)
                        except Exception as e:
                            logger.error(f"Phase 1 OCR/Extraction failed: {e}")

                    if not is_satisfactory(best_result):
                        # PHASE 2 — Fallback documents (Phase 1 pages are not re-OCR'd)
                        logger.debug("[Phase 1] Result unsatisfactory. Triggering fallback...")
                        emit_event("claim_step", step="downloading fallback documents")
                        try:
                            phase2_new_pages = download_and_normalize(FALLBACK_DOCS, documents, claim_folder, pages_folder, processed_hashes)
                        except Exception as e:
                            logger.error(f"Phase 2 document processing failed: {e}")
                            phase2_new_pages = []

                        if phase2_new_pages:
                            emit_event("claim_step", step="reading fallback documents")
                            try:
                                phase2_result, phase2_metrics = ocr_and_extract(phase2_new_pages)
                                all_ocr_metrics.extend(phase2_metrics)
                            except Exception as e:
                                logger.error(f"Phase 2 OCR/Extraction failed: {e}")
                                phase2_result = None

                            if is_satisfactory(phase2_result):
                                best_result = phase2_result
                            elif phase2_result and phase2_result.get("relevant") and not is_satisfactory(best_result):
                                best_result = phase2_result
                        else:
                            logger.debug("[Phase 2] No new pages could be downloaded/normalised.")
                    else:
                        logger.debug("[Phase 1] SUCCESS - satisfactory result obtained.")

                    result_info = write_result(df, index, best_result, all_ocr_metrics)

                except Exception as e:
                    logger.error(f"Error processing {ack_no}: {e}")
                    df.loc[index, "online_verification_status"] = STATUS_ERROR
                    df.loc[index, "manual_review"] = "YES"
                    result_info = {"status": STATUS_ERROR, "accuracy": 0, "manual_review": True,
                                   "college": "", "via_cache": False, "error": str(e)}
                finally:
                    if new_page is not None:
                        try:
                            new_page.close()
                        except Exception:
                            pass

                save_with_retry(df, output_excel_file, target_sheet_name)
                logger.debug(f"Saved progress after {ack_no}")

                if delete_downloads:
                    shutil.rmtree(claim_folder, ignore_errors=True)

                summary[result_info["status"]] += 1
                summary["processed"] += 1
                if result_info["manual_review"]:
                    summary["manual_review"] += 1
                if result_info.get("via_cache"):
                    summary["cache_hits"] += 1
                emit_event("claim_done", n=n, total=total, ack=ack_no, **result_info)
                main_pbar.update(1)

    save_with_retry(df, output_excel_file, target_sheet_name)
    if stop_file and os.path.exists(stop_file):
        os.remove(stop_file)

    emit_event("run_end", stopped=stopped, total=total, output_file=output_excel_file, summary=summary)
    logger.debug("Done.")
    logger.debug(f"Output saved to {output_excel_file}")


if __name__ == "__main__":
    main()

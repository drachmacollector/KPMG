import pandas as pd
from playwright.sync_api import sync_playwright
import time
import re
import os
import urllib.request
import urllib.error
import socket
from tqdm import tqdm
from bs4 import BeautifulSoup
from document_processor import normalize_document
from document_processor import calculate_sha256
from logger_config import logger

from ocr_engine import ocr_image
from extractor import extract_information, is_satisfactory
from web_resolver import resolve_institution

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

excel_file = "26673- Master Merged Data Final_01.03.2026.xlsx"
target_sheet_name = "Test Data"

# Rows with accuracy below this threshold are flagged for manual review.
# Adjust between 0 and 100 as needed.
ACCURACY_THRESHOLD = 80

# ---------------------------------------------------------------------------

logger.debug("[*] Initializing MAHABOCW Verification Engine...")
with tqdm(total=2, desc="Initialization", bar_format="{l_bar}{bar:20}|", colour="green") as pbar:
    output_excel_file = "Test_Data_Medical_Claim_Data_Output.xlsx"
    if os.path.exists(output_excel_file):
        excel_info = pd.ExcelFile(output_excel_file)
        logger.debug(f"Found existing output file. Sheets: {excel_info.sheet_names}")
        pbar.update(1)

        logger.debug(f"Reading data from sheet: '{target_sheet_name}'...")
        df = pd.read_excel(output_excel_file, sheet_name=target_sheet_name)
    else:
        excel_info = pd.ExcelFile(excel_file)
        logger.debug(f"Sheets found in your Excel file: {excel_info.sheet_names}")
        pbar.update(1)

        logger.debug(f"Reading data from sheet: '{target_sheet_name}'...")
        df = pd.read_excel(excel_file, sheet_name=target_sheet_name)
        
    df.columns = df.columns.str.strip()
    
    logger.debug("Columns Pandas actually sees:")
    logger.debug(df.columns.tolist())
    pbar.update(1)
# ----------------------
cols_to_init = [
    'corrected_college_name',
    'corrected_college_address',
    'accuracy',
    'manual_review',
    'online_verification_status'
]

for col in cols_to_init:
    if col not in df.columns:
        df[col] = ""
    # Explicitly enforce string dtype to prevent float64 rejection on empty columns
    df[col] = df[col].fillna("").astype(str)


def download_document(url, save_path):
    retries = 3
    delays = [2, 4]  # Wait 2s, then 4s on failures.
    
    for attempt in range(retries):
        try:
            urllib.request.urlretrieve(url, save_path)
            logger.debug(f"Downloaded: {save_path}")
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
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


def save_with_retry(df, filename, sheet_name):
    while True:
        try:
            df.to_excel(
                filename,
                sheet_name=sheet_name,
                index=False
            )
            logger.info("[OK] Progress Saved\n")
            return
        except PermissionError:
            logger.info("- Output Excel file is currently open. Retrying...")
            time.sleep(5)


os.makedirs("downloads", exist_ok=True)


# ---------------------------------------------------------------------------
# ACCURACY SCORING
# ---------------------------------------------------------------------------

def compute_accuracy(ocr_metrics_list, llm_result, resolved=None):
    """
    Compute a programmatic accuracy score (0-100) from objective signals.

    Parameters
    ----------
    ocr_metrics_list : list[dict]
        One dict per processed page, each containing:
          avg_confidence, min_confidence, high_conf_ratio, line_count,
          is_relevant (bool — True only if the LLM identified the page as
          a Bonafide Certificate or Student Identity Card).
        (as returned by ocr_and_extract).
    llm_result : dict | None
        The best LLM extraction result for the claim.
    resolved : dict | None
        The dict returned by resolve_institution().  If provided and
        resolution_failed is False, the verification bonus is granted
        as a graduated score based on match_confidence.

    Returns
    -------
    int
        Accuracy score 0-100.

    Scoring breakdown (100 points total):
      OCR avg_confidence              (30 pts max)
        avg_conf * 30                 -> 0-30 pts   (linear, capped)

      Web Verification confidence     (40 pts max)
        round((match_confidence/100) * 40)  -> 0-40 pts  (graduated)
        e.g. 100% match = 40 pts, 75% match = 30 pts, failed = 0 pts
        Cache hits receive match_confidence=100 -> full 40 pts

      Cross-Document Agreement        (30 pts max)
        >= 2 docs with is_relevant=True  -> 30 pts  (full bonus)
        exactly 1 doc with is_relevant=True -> 15 pts (partial)
        no relevant docs                 ->  0 pts
        NOTE: Aadhaar, Ration Card, Self Declaration are readable but
        NOT relevant — they do not count toward this score.
    """
    # --- Component 1: OCR confidence (30 pts) ---
    if ocr_metrics_list:
        avg_conf = sum(m["avg_confidence"] for m in ocr_metrics_list) / len(ocr_metrics_list)
    else:
        avg_conf = 0.0

    ocr_score = min(round(avg_conf * 30), 30)

    # --- Component 2: Graduated web verification score (40 pts) ---
    if resolved is not None and not resolved.get("resolution_failed", True):
        match_confidence = resolved.get("match_confidence", 0)
        verification_score = round((match_confidence / 100) * 40)
    else:
        verification_score = 0

    # --- Component 3: Cross-document agreement (30 pts) ---
    # Only pages identified as Bonafide or Student ID by the LLM count.
    # Irrelevant but readable docs (Aadhaar, Ration Card, Self Declaration)
    # must NOT contribute to this score.
    relevant_docs = sum(
        1 for m in ocr_metrics_list
        if m.get("is_relevant") and m.get("line_count", 0) > 0
    )
    if relevant_docs >= 2:
        cross_doc_score = 30
    elif relevant_docs == 1:
        cross_doc_score = 15
    else:
        cross_doc_score = 0

    total = min(ocr_score + verification_score + cross_doc_score, 100)
    return total


# ---------------------------------------------------------------------------
# Download a subset of documents and return pages for those successfully
# normalised. Deduplication is handled via SHA-256.
# ---------------------------------------------------------------------------
def download_and_normalize(doc_subset, documents, claim_folder, pages_folder, processed_hashes):
    """Download `doc_subset` keys from `documents`, normalize, return page list."""
    new_pages = []
    skipped = []
    downloaded_count = 0

    for doc_type in doc_subset:
        url = documents.get(doc_type)
        if not url:
            skipped.append(doc_type.replace('_', ' ').title())
            continue

        logger.debug(f"[*] Downloading {doc_type.replace('_', ' ').title()}...")
        extension = url.split("?")[0].split(".")[-1]
        output_path = os.path.join(claim_folder, f"{doc_type}.{extension}")

        if not download_document(url, output_path):
            continue

        logger.info(f"[OK] {doc_type.replace('_', ' ').title()} downloaded")

        file_hash = calculate_sha256(output_path)
        if file_hash in processed_hashes:
            logger.debug(f"Duplicate skipped: {doc_type}.{extension}")
            continue

        processed_hashes[file_hash] = f"{doc_type}.{extension}"
        downloaded_count += 1

        pages = normalize_document(
            output_path,
            pages_folder,
            os.path.splitext(f"{doc_type}.{extension}")[0]
        )
        new_pages.extend(pages)
        logger.debug(f"{doc_type}.{extension} -> {len(pages)} page(s)")

    if skipped:
        for skip_doc in skipped:
            logger.info(f"- {skip_doc} not uploaded")
    if downloaded_count > 0:
        logger.debug(f"[*] Downloaded {downloaded_count}/{len(doc_subset)} documents")

    return new_pages


def ocr_and_extract(page_paths):
    """
    OCR each page and run LLM extraction.

    Returns
    -------
    tuple(dict | None, list[dict])
        (best_result, all_ocr_metrics)
        best_result      — best LLM result (bonafide preferred over student_id)
        all_ocr_metrics  — list of per-page OCR metric dicts for accuracy scoring.
                           Each dict includes 'is_relevant' (bool): True only
                           when the LLM identified the page as a Bonafide
                           Certificate or Student Identity Card.
    """
    bonafide_result = None
    student_id_result = None
    all_ocr_metrics = []

    logger.info("\nRunning OCR...")

    for page in page_paths:
        logger.debug(f"OCR -> {page}")

        ocr_result = ocr_image(page)

        # Collect metrics for every page; is_relevant will be filled in below
        page_metrics = {
            "avg_confidence":  ocr_result["avg_confidence"],
            "min_confidence":  ocr_result["min_confidence"],
            "high_conf_ratio": ocr_result["high_conf_ratio"],
            "line_count":      ocr_result["line_count"],
            "is_relevant":     False,   # default; updated if LLM confirms relevance
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

        # Backfill is_relevant onto the metrics entry for this page
        if result.get("relevant"):
            page_metrics["is_relevant"] = True
            doc_type_display = result["document_type"].replace('_', ' ').title()
            logger.info(f"[OK] Relevant document: {doc_type_display}")

        if not result.get("relevant"):
            continue

        if result["document_type"] == "bonafide":
            if bonafide_result is None:
                bonafide_result = result

        elif result["document_type"] == "student_id":
            if student_id_result is None:
                student_id_result = result

    best_result = bonafide_result or student_id_result
    
    if best_result:
        logger.debug("College extracted successfully.")
    else:
        logger.info("- No relevant document found")
        
    return best_result, all_ocr_metrics


def write_result(df, index, best_result, ocr_metrics):
    """Write extraction result and accuracy score into the dataframe row."""
    resolved = None

    if best_result and best_result.get("relevant"):
        college_name    = (best_result.get("college_name")    or "").strip()
        college_address = (best_result.get("college_address") or "").strip()

        # ------------------------------------------------------------------
        # Online Institution Resolution
        # Pass the noisy Qwen output through the web resolver to get the
        # verified official name and address.  On any failure the resolver
        # returns the original values and sets resolution_failed=True.
        # ------------------------------------------------------------------
        try:
            logger.info(f"\nOCR/Qwen Extracted Name: {college_name}")
            logger.info("\nVerifying College via LLM Search...")
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
        df.loc[index, "online_verification_status"] = "FAILED" if resolved.get("resolution_failed") else ""

    accuracy = compute_accuracy(ocr_metrics, best_result, resolved)
    df.loc[index, "accuracy"] = f"{accuracy}%"

    # Flag for manual review when accuracy is below the threshold
    # OR when no usable result was obtained at all.
    needs_review = (accuracy < ACCURACY_THRESHOLD) or (not best_result) or (not best_result.get("relevant"))
    df.loc[index, "manual_review"] = "YES" if needs_review else ""

    if resolved and not resolved.get("resolution_failed"):
        v_name = (resolved.get("verified_college_name") or "").upper()
        v_addr = (resolved.get("verified_college_address") or "").upper()
        logger.info(f"\n[OK] College Verified")
        logger.info(v_name)
        if v_addr:
            logger.info(v_addr)
        logger.info(f"\nAccuracy: {accuracy}%")
        logger.info(f"Manual Review: {'Yes' if needs_review else 'No'}\n")
    else:
        logger.info(f"\n[FAILED] Resolution Failed\n")
        logger.info(f"Accuracy: {accuracy}%")
        logger.info(f"Manual Review: {'Yes' if needs_review else 'No'}\n")


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


# 2. Start Browser Automation
with sync_playwright() as p:
    # no_viewport=True allows you to maximize the window safely without breaking the site!  
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(no_viewport=True)
    page = context.new_page()

    page.goto(
        "https://iwbms.mahabocw.in/sso",
        wait_until="domcontentloaded",
        timeout=60000
    )

    # --- THE HUMAN HANDOFF ---
    logger.info("\n------------------------------------------------------------\n")
    logger.info("Human Setup Required")
    logger.info("- Preferably don't maximize or resize the window")
    logger.info("- Log in manually")
    logger.info("- Click on the 'Claims' section")
    logger.info("- Drag the 'Acknowledgement Number' column into view")
    logger.info("- Click the 3 bars on the column, click the funnel, and leave the text box open\n")

    input("Press ENTER here in the terminal when you are ready to start the loop...")
    logger.debug("Starting automated extraction...")

    rows_to_process = pd.concat([
    df.iloc[31:376],    # Excel rows 2–30
    ])
    
    with tqdm(
        total=len(rows_to_process),
        desc="Overall Progress",
        bar_format="{l_bar}{bar:20}| {n_fmt}/{total_fmt}",
        colour="green"
    ) as main_pbar:
        for index, row in rows_to_process.iterrows():
            ack_no = str(row['acknowledgement_no']).strip()

            claim_folder = os.path.join("downloads", ack_no)
            os.makedirs(claim_folder, exist_ok=True)

            # Skip already processed rows
            if (
                pd.notna(row["corrected_college_name"])
                and str(row["corrected_college_name"]).strip()
            ):
                logger.debug(f"Row {ack_no} already processed, skipping.")
                main_pbar.update(1)
                continue

            logger.info("\n------------------------------------------------------------\n")
            logger.info("Claim")
            logger.info(f"Acknowledgement: {ack_no}\n")

            try:
                # --- FILTER MENU HANDLING ---
                filter_box = page.locator('input[type="text"]:visible').first
    
                if not filter_box.is_visible(timeout=2000):
                    ack_header = page.locator('.ag-header-cell', has_text=re.compile(r"acknowledgement", re.IGNORECASE)).first
                    ack_header.hover()
                    ack_header.locator('.ag-icon-menu').first.click()
                    time.sleep(1)
    
                # 1. Type the new number
                filter_box.fill(ack_no)
    
                # 2. Click Apply Filter
                page.locator('button').filter(has_text="Apply").first.click()
                logger.debug("Filtering through claims...")
                time.sleep(3)
    
            # --- NEW TAB HANDLING ---
                with context.expect_page() as new_page_info:
                    page.locator('a, button').filter(has_text="View claim form").first.click()
    
                new_page = new_page_info.value
    
                # Wait for page to finish loading
                logger.debug("Claim form opened")
                new_page.wait_for_selector("label", timeout=20000)
                time.sleep(1)
    
                html = new_page.content()
                soup = BeautifulSoup(html, "html.parser")
                labels = soup.find_all("label")
                documents = {}
    
                for label in labels:
                    text = label.get_text(" ", strip=True).lower()
                    a = label.find_next("a", href=True)
    
                    if not a:
                        continue
    
                    if "education self declaration" in text:
                        documents["education_self_declaration"] = a["href"]
                    elif "bonafide certificate" in text:
                        documents["bonafide"] = a["href"]
                    elif "college identity" in text:
                        documents["college_id"] = a["href"]
                    elif "aadhaar card" in text:
                        documents["aadhaar"] = a["href"]
                    elif "ration card" in text:
                        documents["ration"] = a["href"]
                    elif (
                        text.startswith("5. self declaration")
                        or (
                            "self declaration" in text
                            and "education self declaration" not in text
                        )
                    ):
                        documents["self_declaration"] = a["href"]
    
                logger.info("Documents Found")
                for doc_key in documents.keys():
                    doc_display = doc_key.replace('_', ' ').title()
                    logger.info(f"[OK] {doc_display}")
                logger.info("\nDownloading Documents...")
    
                pages_folder = os.path.join(claim_folder, "pages")
                os.makedirs(pages_folder, exist_ok=True)
    
                # Shared deduplication tracker across both phases
                processed_hashes = {}
    
                # Accumulate OCR metrics across both phases for accuracy scoring
                all_ocr_metrics = []
    
                # ---------------------------------------------------------------
                # PHASE 1 — Fast path: Bonafide + College ID only
                # ---------------------------------------------------------------
                logger.debug("[Phase 1] Trying priority documents (Bonafide + College ID)...")
                try:
                    phase1_pages = download_and_normalize(
                        PRIORITY_DOCS, documents, claim_folder, pages_folder, processed_hashes
                    )
                except Exception as e:
                    logger.error(f"Phase 1 document processing failed: {e}")
                    phase1_pages = []
    
                best_result = None
    
                if phase1_pages:
                    logger.debug(f"[Phase 1] Found {len(phase1_pages)} page(s) to process.")
                    try:
                        best_result, phase1_metrics = ocr_and_extract(phase1_pages)
                        all_ocr_metrics.extend(phase1_metrics)
                    except Exception as e:
                        logger.error(f"Phase 1 OCR/Extraction failed: {e}")
    
                if is_satisfactory(best_result):
                    logger.debug("[Phase 1] SUCCESS - satisfactory result obtained.")
                    write_result(df, index, best_result, all_ocr_metrics)
    
                else:
                    # ---------------------------------------------------------------
                    # PHASE 2 — Fallback: download remaining documents
                    #            Reuse already-OCR'd Phase 1 pages (no duplicate OCR)
                    # ---------------------------------------------------------------
                    logger.debug("[Phase 1] Result unsatisfactory. Triggering fallback...")
                    logger.debug("[Phase 2] Downloading fallback documents...")
    
                    try:
                        phase2_new_pages = download_and_normalize(
                            FALLBACK_DOCS, documents, claim_folder, pages_folder, processed_hashes
                        )
                    except Exception as e:
                        logger.error(f"Phase 2 document processing failed: {e}")
                        phase2_new_pages = []
    
                    if phase2_new_pages:
                        logger.debug(f"[Phase 2] Found {len(phase2_new_pages)} new page(s) to process.")
                        try:
                            phase2_result, phase2_metrics = ocr_and_extract(phase2_new_pages)
                            all_ocr_metrics.extend(phase2_metrics)
                        except Exception as e:
                            logger.error(f"Phase 2 OCR/Extraction failed: {e}")
                            phase2_result = None
    
                        # Prefer Phase 2 result if satisfactory; else keep Phase 1 result
                        if is_satisfactory(phase2_result):
                            best_result = phase2_result
                            logger.debug("[Phase 2] SUCCESS - satisfactory result from fallback docs.")
                        elif phase2_result and phase2_result.get("relevant"):
                            if not is_satisfactory(best_result):
                                best_result = phase2_result
                            logger.debug("[Phase 2] Partial result - using best available.")
                        else:
                            logger.debug("[Phase 2] No improvement from fallback docs.")
                    else:
                        logger.debug("[Phase 2] No new pages could be downloaded/normalised.")
    
                    write_result(df, index, best_result, all_ocr_metrics)
    
                save_with_retry(
                    df,
                    "Test_Data_Medical_Claim_Data_Output.xlsx",
                    target_sheet_name
                )
    
                logger.debug(f"Saved progress after {ack_no}")
    
                # Close the claim form tab
                new_page.close()
                main_pbar.update(1)
    
            except Exception as e:
                logger.error(f"Error processing {ack_no}: {e}")
                main_pbar.update(1)
                continue

save_with_retry(
    df,
    "Test_Data_Medical_Claim_Data_Output.xlsx",
    target_sheet_name
)

logger.debug("Done.")
logger.debug("Output saved to Test_Data_Medical_Claim_Data_Output.xlsx")

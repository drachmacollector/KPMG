import pandas as pd
from playwright.sync_api import sync_playwright
import time
import re
import os
import urllib.request
from tqdm import tqdm
from bs4 import BeautifulSoup
from document_processor import normalize_document
from document_processor import calculate_sha256

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

excel_info = pd.ExcelFile(excel_file)
print(f"\n 📃 Sheets found in your Excel file: {excel_info.sheet_names}")

print(f"📖 Reading data from sheet: '{target_sheet_name}'...")
df = pd.read_excel(excel_file, sheet_name=target_sheet_name)

df.columns = df.columns.str.strip()

# Print out exactly what Pandas thinks your columns are
print("\n🔍 Columns Pandas actually sees:")
print(df.columns.tolist())
print("-" * 50 + "\n")
# ----------------------

if 'corrected_college_name' not in df.columns:
    df['corrected_college_name'] = ""

if 'corrected_college_address' not in df.columns:
    df['corrected_college_address'] = ""

if 'accuracy' not in df.columns:
    df['accuracy'] = ""

if 'manual_review' not in df.columns:
    df['manual_review'] = ""

if 'online_verification_status' not in df.columns:
    df['online_verification_status'] = ""


def download_document(url, save_path):
    try:
        urllib.request.urlretrieve(url, save_path)
        print(f"Downloaded: {save_path}")
        return True

    except Exception as e:
        print(f"Download failed: {e}")
        return False


def save_with_retry(df, filename, sheet_name):
    while True:
        try:
            df.to_excel(
                filename,
                sheet_name=sheet_name,
                index=False
            )
            print("Progress saved.")
            return
        except PermissionError:
            print("\n⚠️ Output Excel file is currently open.")
            print("Please close it. Retrying in 5 seconds...")
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

    for doc_type in tqdm(
        doc_subset,
        desc="Downloading",
        unit="doc",
        leave=False,
        colour="cyan"
        ):
        url = documents.get(doc_type)
        if not url:
            print(f"  [{doc_type}] not found in documents dict, skipping.")
            continue

        extension = url.split("?")[0].split(".")[-1]
        output_path = os.path.join(claim_folder, f"{doc_type}.{extension}")

        if not download_document(url, output_path):
            continue

        file_hash = calculate_sha256(output_path)
        if file_hash in processed_hashes:
            print(f"  Duplicate skipped: {doc_type}.{extension}")
            continue

        processed_hashes[file_hash] = f"{doc_type}.{extension}"

        pages = normalize_document(
            output_path,
            pages_folder,
            os.path.splitext(f"{doc_type}.{extension}")[0]
        )
        new_pages.extend(pages)
        print(f"  {doc_type}.{extension} -> {len(pages)} page(s)")

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

    for page in page_paths:
        print(f"\n  OCR -> {page}")

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
            print(f"  No text detected on {page}.")
            continue

        print(
            f"  OCR metrics — avg_conf={ocr_result['avg_confidence']:.2%}  "
            f"min_conf={ocr_result['min_confidence']:.2%}  "
            f"high_ratio={ocr_result['high_conf_ratio']:.2%}  "
            f"lines={ocr_result['line_count']}"
        )

        try:
            result = extract_information(ocr_text)
        except Exception as e:
            print(f"  LLM failed on {page}: {e}")
            continue

        print(f"  {result}")

        # Backfill is_relevant onto the metrics entry for this page
        if result.get("relevant"):
            page_metrics["is_relevant"] = True

        if not result.get("relevant"):
            continue

        if result["document_type"] == "bonafide":
            if bonafide_result is None:
                bonafide_result = result

        elif result["document_type"] == "student_id":
            if student_id_result is None:
                student_id_result = result

    best_result = bonafide_result or student_id_result
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
        resolved = resolve_institution(
            extracted_name=college_name,
            extracted_address=college_address,
        )

        df.loc[index, "corrected_college_name"]    = resolved["verified_college_name"].upper()
        df.loc[index, "corrected_college_address"] = resolved["verified_college_address"].upper()
        df.loc[index, "online_verification_status"] = "FAILED" if resolved["resolution_failed"] else ""

    accuracy = compute_accuracy(ocr_metrics, best_result, resolved)
    df.loc[index, "accuracy"] = f"{accuracy}%"

    # Flag for manual review when accuracy is below the threshold
    # OR when no usable result was obtained at all.
    needs_review = (accuracy < ACCURACY_THRESHOLD) or (not best_result) or (not best_result.get("relevant"))
    df.loc[index, "manual_review"] = "YES" if needs_review else ""

    print(f"  Accuracy: {accuracy}%  |  Manual review: {'YES' if needs_review else 'NO'}")


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

    page.goto("https://iwbms.mahabocw.in/sso")

    # --- THE HUMAN HANDOFF ---
    print("\n" + "="*50)
    print("⏸️ AI PAUSED FOR HUMAN SETUP")
    print("1. Preferably don't maximize or resize the window.")
    print("2. Log in manually.")
    print("3. Click on the 'Claims' section.")
    print("4. Drag the 'Acknowledgement Number' column into view.")
    print("5. Click the 3 bars on the column, click the funnel, and leave the text box open.")
    print("="*50 + "\n")

    input("👉 Press ENTER here in the terminal when you are ready to start the loop...")
    print("Starting automated extraction...")

    # for index, row in df.head(5).iterrows():
    for index, row in df.iloc[14:23].iterrows():
        ack_no = str(row['acknowledgement_no']).strip()

        claim_folder = os.path.join("downloads", ack_no)
        os.makedirs(claim_folder, exist_ok=True)

        # Skip already processed rows
        if (
            pd.notna(row["corrected_college_name"])
            and str(row["corrected_college_name"]).strip()
        ):
            print(f"Row {index + 1} ({ack_no}) already processed, skipping.")
            continue

        print(f"\n{'='*60}")
        print(f"🔃 Processing Row {index + 1}: {ack_no}")
        print(f"{'='*60}")

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
            print("Filtering through claims...")
            time.sleep(3)

        # --- NEW TAB HANDLING ---
            with context.expect_page() as new_page_info:
                page.locator('a, button').filter(has_text="View claim form").first.click()

            new_page = new_page_info.value

            # Wait for page to finish loading
            print("Claim form opened ")
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

            print(f"📜 Documents found: {list(documents.keys())}")

            pages_folder = os.path.join(claim_folder, "pages")
            os.makedirs(pages_folder, exist_ok=True)

            # Shared deduplication tracker across both phases
            processed_hashes = {}

            # Accumulate OCR metrics across both phases for accuracy scoring
            all_ocr_metrics = []

            # ---------------------------------------------------------------
            # PHASE 1 — Fast path: Bonafide + College ID only
            # ---------------------------------------------------------------
            print("\n[Phase 1] 🔄️ Downloading priority documents (bonafide + college_id)...")
            phase1_pages = download_and_normalize(
                PRIORITY_DOCS, documents, claim_folder, pages_folder, processed_hashes
            )

            best_result = None

            if phase1_pages:
                print(f"\n[Phase 1]⏳ Running OCR + LLM on {len(phase1_pages)} page(s)...")
                best_result, phase1_metrics = ocr_and_extract(phase1_pages)
                all_ocr_metrics.extend(phase1_metrics)

            if is_satisfactory(best_result):
                print("\n[Phase 1] SUCCESS — satisfactory result obtained.")
                write_result(df, index, best_result, all_ocr_metrics)

            else:
                # ---------------------------------------------------------------
                # PHASE 2 — Fallback: download remaining documents
                #            Reuse already-OCR'd Phase 1 pages (no duplicate OCR)
                # ---------------------------------------------------------------
                print("\n[Phase 1] Result unsatisfactory. Triggering fallback...")
                print("[Phase 2] Downloading fallback documents...")

                phase2_new_pages = download_and_normalize(
                    FALLBACK_DOCS, documents, claim_folder, pages_folder, processed_hashes
                )

                if phase2_new_pages:
                    print(f"\n[Phase 2] Running OCR + LLM on {len(phase2_new_pages)} new page(s)...")
                    phase2_result, phase2_metrics = ocr_and_extract(phase2_new_pages)
                    all_ocr_metrics.extend(phase2_metrics)

                    # Prefer Phase 2 result if satisfactory; else keep Phase 1 result
                    if is_satisfactory(phase2_result):
                        best_result = phase2_result
                        print("[Phase 2] SUCCESS — satisfactory result from fallback docs.")
                    elif phase2_result and phase2_result.get("relevant"):
                        if not is_satisfactory(best_result):
                            best_result = phase2_result
                        print("[Phase 2] Partial result — using best available.")
                    else:
                        print("[Phase 2] No improvement from fallback docs.")
                else:
                    print("[Phase 2] No new pages could be downloaded/normalised.")

                write_result(df, index, best_result, all_ocr_metrics)

            save_with_retry(
                df,
                "Test_Data_Medical_Claim_Data_Output.xlsx",
                target_sheet_name
            )

            print(f"\nSaved progress after {ack_no} 🗃️")

            # Close the claim form tab
            new_page.close()

        except Exception as e:
            print(f"Error processing {ack_no}: {e}")
            continue

save_with_retry(
    df,
    "Test_Data_Medical_Claim_Data_Output.xlsx",
    target_sheet_name
)

print("\nDone.")
print("Output saved to Test_Data_Medical_Claim_Data_Output.xlsx")
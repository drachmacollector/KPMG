import pandas as pd
from playwright.sync_api import sync_playwright
import time
import re
import os
import urllib.request
from bs4 import BeautifulSoup
from document_processor import normalize_document
from document_processor import calculate_sha256

from ocr_engine import ocr_image
from extractor import extract_information, is_satisfactory

excel_file = "Medical_Claim_Data_Part_1.xlsx"
excel_info = pd.ExcelFile(excel_file)
print(f"\n Sheets found in your Excel file: {excel_info.sheet_names}")

target_sheet_name = "Medical Data Verification-Par1"

print(f"Reading data from sheet: '{target_sheet_name}'...")
df = pd.read_excel(excel_file, sheet_name=target_sheet_name)

df.columns = df.columns.str.strip()

# Print out exactly what Pandas thinks your columns are
print("\n Columns Pandas actually sees:")
print(df.columns.tolist())
print("-" * 50 + "\n")
# ----------------------

if 'corrected_college_name' not in df.columns:
    df['corrected_college_name'] = ""

if 'corrected_college_address' not in df.columns:
    df['corrected_college_address'] = ""

if 'manual_review' not in df.columns:
    df['manual_review'] = ""

def download_document(url, save_path):
    try:
        urllib.request.urlretrieve(url, save_path)
        print(f"Downloaded: {save_path}")
        return True

    except Exception as e:
        print(f"Download failed: {e}")
        return False


os.makedirs("downloads", exist_ok=True)


# ---------------------------------------------------------------------------
# Download a subset of documents and return (pages, raw_file_paths) for those
# that were successfully normalised.  Deduplication is handled via SHA-256.
# ---------------------------------------------------------------------------
def download_and_normalize(doc_subset, documents, claim_folder, pages_folder, processed_hashes):
    """Download `doc_subset` keys from `documents`, normalize, return page list."""
    new_pages = []

    for doc_type in doc_subset:
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
    """OCR each page and run LLM extraction. Returns best result or None."""
    bonafide_result = None
    student_id_result = None

    for page in page_paths:
        print(f"\n  OCR -> {page}")

        text = ocr_image(page)

        if not text.strip():
            continue

        try:
            result = extract_information(text)
        except Exception as e:
            print(f"  LLM failed on {page}: {e}")
            continue

        print(f"  {result}")

        if not result.get("relevant"):
            continue

        if result["document_type"] == "bonafide":
            if bonafide_result is None:
                bonafide_result = result

        elif result["document_type"] == "student_id":
            if student_id_result is None:
                student_id_result = result

    if bonafide_result:
        return bonafide_result
    if student_id_result:
        return student_id_result
    return None


def write_result(df, index, best_result):
    """Write extraction result into the dataframe row."""
    if best_result:
        college_name = (best_result.get("college_name") or "").strip()
        college_address = (best_result.get("college_address") or "").strip()

        df.loc[index, "corrected_college_name"] = college_name.upper()
        df.loc[index, "corrected_college_address"] = college_address.upper()
        df.loc[index, "manual_review"] = ""
    else:
        df.loc[index, "manual_review"] = "YES"


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
    print("AI PAUSED FOR HUMAN SETUP")
    print("1. Maximize the window now if you want to.")
    print("2. Log in manually.")
    print("3. Click on the 'Claims' section.")
    print("4. Drag the 'Acknowledgement Number' column into view.")
    print("5. Click the 3 bars on the column, click the funnel, and leave the text box open.")
    print("="*50 + "\n")

    input("Press ENTER here in the terminal when you are ready to start the loop...")
    print("Starting automated extraction...")

    # Process up to row index 3 (ack_no 7791074215 is at index 2, so head(4) includes it)
    for index, row in df.head(4).iterrows():
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
        print(f"Processing Row {index + 1}: {ack_no}")
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
            print("Waiting for grid to filter...")
            time.sleep(3)

        # --- NEW TAB HANDLING ---
            with context.expect_page() as new_page_info:
                page.locator('a, button').filter(has_text="View claim form").first.click()

            new_page = new_page_info.value

            # Wait for page to finish loading
            print("Claim form opened.")
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

            print(f"Documents found: {list(documents.keys())}")

            pages_folder = os.path.join(claim_folder, "pages")
            os.makedirs(pages_folder, exist_ok=True)

            # Shared deduplication tracker across both phases
            processed_hashes = {}

            # ---------------------------------------------------------------
            # PHASE 1 — Fast path: Bonafide + College ID only
            # ---------------------------------------------------------------
            print("\n[Phase 1] Downloading priority documents (bonafide + college_id)...")
            phase1_pages = download_and_normalize(
                PRIORITY_DOCS, documents, claim_folder, pages_folder, processed_hashes
            )

            best_result = None

            if phase1_pages:
                print(f"\n[Phase 1] Running OCR + LLM on {len(phase1_pages)} page(s)...")
                best_result = ocr_and_extract(phase1_pages)

            if is_satisfactory(best_result):
                print("\n[Phase 1] SUCCESS — satisfactory result obtained.")
                write_result(df, index, best_result)

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
                    # Combine Phase 1 pages (already OCR'd above) with new pages.
                    # We only need to OCR the NEW pages; pass the combined set for
                    # a single unified selection pass.
                    print(f"\n[Phase 2] Running OCR + LLM on {len(phase2_new_pages)} new page(s)...")
                    phase2_result = ocr_and_extract(phase2_new_pages)

                    # Prefer Phase 2 result if satisfactory; else keep Phase 1 result
                    # (even if it isn't fully satisfactory, partial data is better than none)
                    if is_satisfactory(phase2_result):
                        best_result = phase2_result
                        print("[Phase 2] SUCCESS — satisfactory result from fallback docs.")
                    elif phase2_result and phase2_result.get("relevant"):
                        # Phase 2 gave a relevant but incomplete result;
                        # use whichever has more data
                        if not is_satisfactory(best_result):
                            best_result = phase2_result
                        print("[Phase 2] Partial result — using best available.")
                    else:
                        print("[Phase 2] No improvement from fallback docs.")
                else:
                    print("[Phase 2] No new pages could be downloaded/normalised.")

                write_result(df, index, best_result)

            df.to_excel(
                "Medical_Claim_Data_Output.xlsx",
                sheet_name=target_sheet_name,
                index=False
            )

            print(f"\nSaved progress after {ack_no}")

            # Close the claim form tab
            new_page.close()

        except Exception as e:
            print(f"Error processing {ack_no}: {e}")
            continue

df.to_excel(
    "Medical_Claim_Data_Output.xlsx",
    sheet_name=target_sheet_name,
    index=False
)

print("\nDone.")
print("Output saved to Medical_Claim_Data_Output.xlsx")
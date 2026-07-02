# MAHABOCW Medical Scholarship Verification Automation

**Project Type:** Intelligent Document Processing (IDP) + Browser Automation
**Language:** Python
**Target Users:** Maharashtra Building & Other Construction Workers Welfare Board (MAHABOCW)
**Status:** Active Development

---

## 1. Project Background and Objective

The Maharashtra Building and Other Construction Workers Welfare Board (MAHABOCW) processes educational assistance and medical scholarship claims submitted by registered construction workers for their children. 

When applying through the MAHABOCW portal, applicants must upload supporting documents such as Bonafide Certificates, College Identity Cards, Aadhaar Cards, Ration Cards, and Self Declarations. However, a significant bottleneck exists: the college information manually entered by applicants is frequently incomplete, abbreviated, misspelled, or entirely incorrect (e.g., entering "AMRAVATI" instead of a full address, or omitting "& Hospital" from the college name).

Currently, consultants manually verify every single application. They open the uploaded Bonafide Certificate, read the college letterhead, and manually type the corrected, official college name and address into a master Excel tracking sheet. With over 21,000 pending applications, this repetitive, manual process is extremely time-consuming and prone to human error.

**The objective of this project is to automate the verification workflow.** The system acts as a complete Intelligent Document Processing (IDP) pipeline that navigates the portal, reads the uploaded documents using OCR, extracts the correct institution details using AI, verifies them against online sources, and outputs a corrected Excel workbook, leaving only uncertain cases for manual review.

---

## 2. System Architecture & Workflow

The architecture is designed as a multi-stage pipeline, blending Playwright-based browser automation with advanced local AI extraction and cloud-based entity resolution. 

### Step 1: Browser Automation & Navigation (`verify_colleges.py`)
Since the MAHABOCW portal is an Angular Single Page Application (SPA), traditional web scraping is insufficient. 
- The system uses **Playwright** to launch a Chromium browser.
- It intentionally pauses to allow the human user to log in manually (handling captchas/security) and configure the Claims grid.
- Once ready, the script iterates through pending claims in the Excel sheet (`26673- Master Merged Data Final_01.03.2026.xlsx`).
- It enters the `acknowledgement_no` into the grid filter, opens the "View Claim Form" in a new tab, and scrapes the URLs for all uploaded applicant documents.
- *Note: Browser automation works reliably; the primary complexity lies in the downstream document processing.*

### Step 2: Smart Document Downloading & Normalization (`document_processor.py`)
Documents are processed in phases to save time and API costs:
- **Phase 1 (Priority):** Attempts to process the "Bonafide Certificate" and "College Identity Card" first.
- **Phase 2 (Fallback):** If Phase 1 yields unsatisfactory results, it falls back to parsing Aadhaar, Ration Cards, or Self Declarations.
- **Deduplication:** A SHA-256 hash is calculated for every downloaded file to prevent processing the same generic document twice.
- **Format Normalization:** PDFs are converted into PNG images using `PyMuPDF (fitz)`.
- **Orientation Correction:** 
  - First, mobile photos tagged sideways are corrected using **EXIF rotation**.
  - Second, a brute-force **PaddleOCR rotation sweep** tests the image at 0°, 90°, 180°, and 270°. The angle yielding the highest OCR confidence score is applied, guaranteeing that downstream text extraction receives upright text.

### Step 3: OCR Engine (`ocr_engine.py`)
This is where the heavy lifting for the IDP pipeline begins. 
- The system uses **PaddleOCR** (with GPU/CUDA acceleration if available) to extract raw text from the normalized images.
- Alongside the text, the engine computes critical quality metrics for each page:
  - `avg_confidence`: Mean per-line confidence score.
  - `min_confidence`: Worst single-line confidence score.
  - `high_conf_ratio`: Fraction of lines with confidence ≥ 0.80.
  - `line_count`: Total lines of text detected.

### Step 4: AI Information Extraction (`extractor.py`)
Raw OCR text is notoriously noisy (missing spaces, capitalization artifacts, character substitutions like "0" for "O"). 
- The raw OCR text is sent to a local LLM via **Ollama** running the `qwen2.5:7b-instruct` model.
- A highly engineered system prompt instructs Qwen to:
  1. Mentally auto-correct common OCR corruptions (e.g., "Shkshan" -> "Shikshan", "Hospita1" -> "Hospital").
  2. Separate the degree-granting college name from the managing organization/charitable trust (e.g., discarding "Late Shri Educational Society's" from the final college name).
  3. Extract the clean `college_name` and complete `college_address`.
- The LLM outputs strict JSON, returning whether the document is relevant and the extracted fields.

### Step 5: Online Institution Resolution (`web_resolver.py`)
Even after LLM extraction, the college name might be slightly inaccurate or lack the official formatting. 
- **Fuzzy Caching:** The extracted name is checked against `institution_cache.json` using RapidFuzz. If a >90% match is found, API calls are bypassed entirely.
- **Web Search:** If no cache hit occurs, the system queries **Google Search (via SerpApi)** using the extracted name and address to find the real-world institution.
- **LLM Ranking & Resolution:** The top 5 search results are sent to a cloud LLM (primarily **Google Gemini 2.5 Flash-Lite**, with a fallback to OpenRouter). The LLM acts as an entity-resolution assistant, selecting the search result that best matches the institution, stripping out web noise (like "- Wikipedia" or "| Official Site"), and extracting the specific city.
- The system safely appends the city to the official college name and updates the local cache.

### Step 6: Accuracy Scoring & Output (`verify_colleges.py`)
To ensure data integrity, the system programmatically computes an **Accuracy Score (0-100)** for every processed claim:
- **OCR Confidence (up to 30 pts):** Based on PaddleOCR's average confidence.
- **Web Verification (up to 40 pts):** Awarded if the online resolution via Google/Gemini was successful.
- **Cross-Document Agreement (up to 30 pts):** Awarded if multiple documents (e.g., both Bonafide and ID card) yield readable text.

The system then updates the target Excel sheet (`Test_Data_Medical_Claim_Data_Output.xlsx`) with:
- `corrected_college_name`
- `corrected_college_address`
- `online_verification_status`
- `accuracy`
- `manual_review`: Flagged as "YES" if the computed accuracy falls below the 80% threshold, ensuring human consultants only spend time on ambiguous or highly corrupted documents.

---

## 3. Technology Stack

- **Browser Automation:** Playwright
- **Document Processing:** PyMuPDF (`fitz`), OpenCV (`cv2`), Pillow (PIL)
- **OCR:** PaddleOCR (with CUDA/GPU support)
- **Local AI (Extraction):** Ollama (`qwen2.5:7b-instruct`)
- **Cloud AI (Resolution):** Google GenAI SDK (`gemini-2.5-flash-lite`, `gemini-2.5-flash`), OpenRouter (fallback)
- **Search API:** SerpApi (Google Search)
- **Data Manipulation:** Pandas (`pd`)
- **Fuzzy Matching:** RapidFuzz

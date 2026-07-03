# MAHABOCW Medical Scholarship Verification Automation

**Project type:** Intelligent Document Processing (IDP) + browser automation  
**Language:** Python  
**Target users:** Maharashtra Building & Other Construction Workers Welfare Board (MAHABOCW) verification team  
**Status:** Active development

---

## 1. Project Objective

This project automates college-name and college-address verification for MAHABOCW medical scholarship claims.

Applicants often enter incomplete, abbreviated, misspelled, or partially incorrect institution details in the MAHABOCW portal. Consultants then have to open uploaded documents manually, read the bonafide certificate or college identity card, correct the college information, and update the tracking workbook.

The automation pipeline reduces that manual workload by:

1. Opening each claim in the MAHABOCW portal through Playwright.
2. Downloading uploaded claim documents.
3. Normalizing PDFs and images into OCR-ready PNG pages.
4. Running PaddleOCR with confidence metrics.
5. Using a local Ollama model to extract structured college details from noisy OCR text.
6. Resolving the extracted institution through Gemini native Google Search grounding, with OpenRouter fallback.
7. Writing verified values, confidence scoring, and manual-review flags back to Excel.

---

## 2. Current Repository Layout

| Path | Purpose |
| --- | --- |
| `verify_colleges.py` | Main orchestration script. Handles Excel I/O, browser automation, document download, phase control, OCR/extraction calls, resolver calls, accuracy scoring, and output writes. |
| `document_processor.py` | Converts PDFs/images into normalized PNG pages, computes SHA-256 hashes, applies EXIF correction, and performs PaddleOCR-based rotation detection. |
| `ocr_engine.py` | Initializes PaddleOCR once, configures CUDA/Paddle runtime compatibility, suppresses noisy Paddle logs, and exposes `ocr_image()`. |
| `extractor.py` | Uses Ollama `qwen2.5:7b-instruct` to classify relevant documents and extract college name/address JSON from OCR text. |
| `web_resolver.py` | Resolves extracted institution details using cache lookup, Gemini native search grounding, confidence scoring, address cleaning, and OpenRouter fallback. |
| `logger_config.py` | Central logging setup. Writes clean console output plus timestamped DEBUG logs under `logs/`. |
| `requirements.txt` | Human-maintained dependency list and installation notes. |
| `requirements-lock.txt` | Frozen environment snapshot. |
| `institution_cache.json` | Local resolver cache used to avoid repeated model/search calls for known institutions. |
| `downloads/` | Per-claim downloaded documents and normalized page images. |
| `testing/` | Test/sample spreadsheets and project PDFs. |

---

## 3. End-to-End Architecture

### Stage 1: Claim Navigation and Document Discovery

Implemented in `verify_colleges.py`.

- Launches Chromium through Playwright in non-headless mode.
- Opens `https://iwbms.mahabocw.in/sso`.
- Pauses for manual login, captcha handling, and AG Grid setup.
- Requires the user to open the Claims section and leave the acknowledgement-number filter box available.
- Iterates over selected rows from the Excel workbook.
- Filters the portal grid by `acknowledgement_no`.
- Opens "View claim form" in a new tab.
- Parses the claim form HTML with BeautifulSoup.
- Collects URLs for:
  - Bonafide Certificate
  - College Identity Card
  - Aadhaar Card
  - Ration Card
  - Self Declaration
  - Education Self Declaration

The current processing window is:

```python
rows_to_process = pd.concat([
    df.iloc[0:30],  # Excel rows 2-30
])
```

### Stage 2: Priority/Fallback Document Processing

Implemented across `verify_colleges.py` and `document_processor.py`.

Documents are processed in two phases to reduce cost and runtime:

| Phase | Documents | Purpose |
| --- | --- | --- |
| Phase 1 | `bonafide`, `college_id` | Fast path for the most reliable institution evidence. |
| Phase 2 | `aadhaar`, `ration`, `self_declaration`, `education_self_declaration` | Fallback only when Phase 1 does not produce satisfactory college name and address. |

For each downloaded document:

- Downloads are retried up to 3 times with small backoff delays.
- A SHA-256 hash is computed to skip duplicate uploads in the same claim.
- PDFs are rendered to 300 DPI PNG pages with PyMuPDF.
- Images are converted to PNG.
- Unsupported formats are skipped.

### Stage 3: Orientation Normalization

Implemented in `document_processor.py`.

The pipeline now uses a two-stage orientation strategy:

1. **EXIF correction:** `PIL.ImageOps.exif_transpose()` fixes mobile photos with orientation metadata.
2. **PaddleOCR rotation sweep:** each page is tested at 0, 90, 180, and 270 degrees. The chosen angle is the one with the best average OCR confidence, with line count as a tiebreaker.

This replaced brittle Tesseract-style orientation detection and keeps OCR orientation logic aligned with the actual OCR engine.

### Stage 4: OCR and OCR Quality Metrics

Implemented in `ocr_engine.py`.

- Initializes PaddleOCR globally so the model is not reloaded for every page.
- Uses GPU/CUDA when PaddlePaddle reports CUDA support.
- Adds NVIDIA package `bin` directories to `PATH` and DLL search paths when available.
- Forces `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` before protobuf imports to avoid PaddlePaddle/google-genai binary protobuf conflicts.
- Uses `use_angle_cls=True` for PaddleOCR's built-in 0/180-degree text-line classifier.
- Suppresses Paddle C++ noise and the recurring "first GPU is used for inference by default" warning.

`ocr_image(image_path)` returns:

```json
{
  "text": "joined OCR text",
  "avg_confidence": 0.0,
  "min_confidence": 0.0,
  "high_conf_ratio": 0.0,
  "line_count": 0
}
```

These metrics are later used for scoring and manual-review decisions.

### Stage 5: Local LLM Extraction

Implemented in `extractor.py`.

The OCR text is sent to Ollama with:

```python
MODEL = "qwen2.5:7b-instruct"
```

The extraction prompt classifies whether a page is relevant:

- Bonafide Certificate
- Student Identity Card
- Irrelevant document such as Aadhaar, Ration Card, or Self Declaration

For relevant documents, the model must return strict JSON:

```json
{
  "relevant": true,
  "document_type": "bonafide",
  "student_name": "...",
  "academic_year": "...",
  "college_name": "...",
  "college_address": "..."
}
```

The prompt includes OCR correction rules for:

- Missing spaces.
- Wrong capitalization.
- Common medical-college spelling corruptions.
- Character substitutions such as `0` vs `O` and `1` vs `I/l`.
- Separating managing trusts or foundations from the actual degree-granting institution.

`is_satisfactory()` only returns true when a relevant result contains both `college_name` and `college_address`.

### Stage 6: Online Institution Resolution

Implemented in `web_resolver.py`.

The resolver has changed from the older SerpApi-plus-ranking flow to a Gemini native-search flow.

Current resolver behavior:

1. Cleans the OCR-extracted address using deterministic regex rules.
2. Checks `institution_cache.json` with RapidFuzz before making model/API calls.
3. Treats cache matches above 90 as trusted matches.
4. Uses Google Gemini with native `google_search` grounding to find the official institution name and full official postal address.
5. Tries Gemini models in fallback order:
   - `gemini-2.0-flash`
   - `gemini-2.5-flash`
   - `gemini-2.5-flash-lite`
   - `gemini-3-flash`
6. Falls back to OpenRouter when all Gemini calls fail.
7. Parses strict JSON from the resolver model.
8. Computes a RapidFuzz token-set confidence score between the verified name and OCR-extracted name.
9. Rejects matches below the configured threshold of 55.
10. Saves accepted matches to `institution_cache.json`.

The resolver now prefers the model/search-provided official address when available. If resolution fails, it falls back to the cleaned OCR address and marks `resolution_failed=True`.

The old SerpApi provider abstraction and query builder are still present in comments/helpers as a future extension point, but SerpApi is not currently wired into `resolve_institution()`.

### Stage 7: Accuracy Scoring and Excel Output

Implemented in `verify_colleges.py`.

Each claim receives an accuracy score from 0 to 100:

| Component | Max points | Current logic |
| --- | ---: | --- |
| OCR confidence | 30 | Average OCR confidence across processed pages, scaled linearly. |
| Web verification | 40 | `match_confidence / 100 * 40` when resolution succeeds. |
| Cross-document agreement | 30 | 30 points for 2+ relevant documents, 15 for 1 relevant document, 0 otherwise. |

Important scoring detail:

- Only pages that the LLM identifies as `bonafide` or `student_id` count as relevant for cross-document agreement.
- Readable but irrelevant Aadhaar, Ration Card, and Self Declaration pages do not increase cross-document agreement.

The output workbook is:

```text
Test_Data_Medical_Claim_Data_Output.xlsx
```

The target sheet is:

```text
Test Data
```

The script creates or updates these output columns:

- `corrected_college_name`
- `corrected_college_address`
- `accuracy`
- `manual_review`
- `online_verification_status`

Rows are flagged for manual review when:

- Accuracy is below `ACCURACY_THRESHOLD` (`80` by default).
- No usable extraction result is found.
- The best extraction result is not relevant.

The script saves progress after every processed claim and retries saves when the Excel output file is open.

---

## 4. Tools and External Services

### Local Tools

- Python
- Playwright Chromium
- PaddleOCR
- PaddlePaddle GPU
- Ollama
- Qwen `qwen2.5:7b-instruct`
- PyMuPDF
- OpenCV
- Pillow
- Pandas
- BeautifulSoup
- RapidFuzz
- tqdm

### Cloud/API Tools

- Google Gen AI SDK (`google-genai`)
- Gemini models with native Google Search grounding
- OpenRouter chat completions fallback

### Environment Variables

The resolver expects API keys from `.env`:

```text
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
```

`OPENROUTER_API_KEY` is only required when Gemini resolution fails and the fallback path is used.

---

## 5. Setup

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

PaddlePaddle GPU is intentionally called out in `requirements.txt` because it depends on the CUDA wheel:

```powershell
pip install paddlepaddle-gpu==2.6.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
```

The project uses `nvidia-cudnn-cu11` so the required cuDNN DLLs can be resolved from the Python environment instead of relying on a system-wide CUDA installation.

Start Ollama and make sure the extraction model is available:

```powershell
ollama pull qwen2.5:7b-instruct
```

Create `.env` in the project root with the resolver keys.

---

## 6. Running the Pipeline

Run:

```powershell
python verify_colleges.py
```

Manual browser setup is part of the workflow:

1. Log in to the MAHABOCW portal manually.
2. Open the Claims section.
3. Bring the Acknowledgement Number column into view.
4. Open its filter menu and leave the text filter box open.
5. Return to the terminal and press Enter.

The script will then process the configured row window, save claim documents under `downloads/`, write logs under `logs/`, update the output Excel file, and continue past individual claim failures where possible.

---

## 7. Operational Notes

- The input workbook is currently `26673- Master Merged Data Final_01.03.2026.xlsx`.
- The output workbook is reused if it already exists, so previously processed rows are preserved and skipped when `corrected_college_name` is already populated.
- The portal automation depends on current MAHABOCW UI labels and AG Grid behavior.
- The pipeline is intentionally semi-automated because portal login/captcha handling remains manual.
- `institution_cache.json`, `downloads/`, and `logs/` are runtime artifacts.
- `requirements-lock.txt` records the current resolved environment but `requirements.txt` is the maintained install guide.

---

## 8. Recent Architecture and Code Changes Captured Here

- Added centralized logging through `logger_config.py`, including timestamped DEBUG log files and cleaner console output.
- Added current runtime folders and artifacts to the architecture notes: `downloads/`, `logs/`, and `institution_cache.json`.
- Documented the current row window in `verify_colleges.py` as Excel rows 2-30.
- Documented retrying document downloads and retrying Excel saves when the output workbook is open.
- Documented duplicate-upload detection with SHA-256.
- Documented the PaddleOCR confidence-based 4-angle rotation sweep.
- Documented Paddle runtime compatibility handling, including NVIDIA DLL path setup and pure-Python protobuf mode.
- Documented the PaddleOCR GPU warning filter added in `ocr_engine.py`.
- Updated the online resolver section to match the current Gemini native-search architecture.
- Removed README claims that SerpApi is currently used in the live resolver path.
- Documented the Gemini model fallback sequence and OpenRouter fallback.
- Documented address cleaning, cache hit behavior, confidence rejection threshold, and cache persistence.
- Clarified that the resolver can now return an official address from native search, falling back to cleaned OCR address only when needed.
- Clarified that irrelevant fallback documents can provide readable text but do not count toward cross-document agreement.

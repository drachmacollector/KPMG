# MAHABOCW Verification Tool — Setup Instructions

Follow these steps once, in order, before using the MAHABOCW Verification Tool for
the first time. After this one-time setup, you'll only ever need step 6.

## Prerequisites

- Windows 10 or later, 64-bit
- At least 16 GB of RAM recommended (the tool runs a local AI model)
- A stable internet connection during setup and during each run
- Your Gemini API key (ask whoever provided this tool if you don't have one yet)

## Step 1 — Install Python

Download and install Python from https://www.python.org/downloads/ (get the same
major version noted in `requirements-lock.txt`, provided alongside this document).
During installation, make sure to check **"Add Python to PATH"**.

## Step 2 — Install the pipeline's Python packages

Open a Command Prompt in the folder where the pipeline files were placed
(the folder containing `verify_colleges.py`) and run:

```
pip install -r requirements-lock.txt
```

This will take several minutes — it downloads a number of large packages.

**If you see errors mentioning CUDA, cuDNN, or NVIDIA:** your computer likely
doesn't have a compatible graphics card. Run these two commands instead, then
retry the install:

```
pip uninstall paddlepaddle-gpu
pip install paddlepaddle
```

## Step 3 — Install the browser automation component

In the same Command Prompt, run:

```
playwright install chromium
```

This downloads a self-contained Chromium browser (roughly 300 MB) used to
navigate the MAHABOCW portal.

## Step 4 — Install and set up the local AI model

1. Download and install Ollama from https://ollama.com/download
2. Once installed, open a new Command Prompt and run:
   ```
   ollama pull qwen2.5:7b-instruct
   ```
   This downloads roughly 4.7 GB and may take a while depending on your
   internet connection. Let it finish completely before continuing.

## Step 5 — Install the MAHABOCW Verification Tool

Run the installer (`MAHABOCW-GUI-Setup.exe`) provided alongside this document,
and follow the on-screen prompts. A shortcut will be created on your Desktop
and in your Start Menu.

## Step 6 — Configure and run

1. Launch **MAHABOCW Verification Tool** from the Desktop or Start Menu.
2. On the Settings screen, fill in:
   - **Pipeline Folder** — the folder from Step 2 (containing `verify_colleges.py`)
   - **Python Interpreter** — leave as `python` unless Step 1 didn't add it to
     PATH, in which case browse to your `python.exe` directly
   - **Input Excel File** — the claims spreadsheet you want to process
   - **Sheet Name** — select from the dropdown once the input file is chosen
   - **Output Excel File** — where the corrected results should be saved
   - **Gemini API Key** — paste your key here
3. Click **Save & Continue**, then click **Start**.
4. A browser window will open automatically. Log into the MAHABOCW portal in
   that window (including any captcha), click the **Claims** section, bring
   the **Acknowledgement Number** column into view, and open its filter box —
   then return to the Verification Tool window and click **"I've logged in —
   Continue"**.
5. The tool will process claims automatically from there. You can **Pause**,
   **Resume**, or **Cancel** at any time from the Run screen — progress is
   saved continuously, so cancelling and restarting later will pick up where
   you left off.
6. When finished, click **Open Output File** to view the results directly.

## Troubleshooting

| Problem | What to do |
|---|---|
| "Output Excel file is currently open" keeps appearing in the log | Close the output file if you have it open in Excel, then wait — the tool retries automatically every few seconds. |
| The browser window doesn't open | Make sure Step 3 completed successfully; try running `playwright install chromium` again. |
| A message about the AI model or Ollama appears | Make sure Ollama is installed and that `ollama pull qwen2.5:7b-instruct` finished completely (Step 4). |
| The tool won't start / interpreter errors | Use the **Test** button next to the Python Interpreter field in Settings to confirm the path is correct. |
| Something else goes wrong mid-run | Click **Open Latest Log File** on the completion screen (or check the `logs` folder inside the pipeline folder) for full details, and share that file when asking for help. |

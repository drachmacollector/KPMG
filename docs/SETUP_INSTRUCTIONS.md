# MAHABOCW Verification Tool — Setup Instructions

Follow these steps once, in order, before using the MAHABOCW Verification Tool for
the first time. After this one-time setup, you'll only ever need step 4.

## Prerequisites

- Windows 10 or later, 64-bit
- At least 16 GB of RAM recommended (the tool runs a local AI model)
- A stable internet connection during setup and during each run
- Your Gemini API key (ask whoever provided this tool if you don't have one yet)
- **Python 3.12 or 3.13** installed with "Add Python to PATH" checked
  (download from https://www.python.org/downloads/ — choose the latest
  stable 3.12.x or 3.13.x release; Python 3.11 has been discontinued as a
  primary download on python.org and is no longer required)

## Step 1 — Install the pipeline

Run **MAHABOCW-Pipeline-Setup.exe** (provided alongside this document) and follow
the on-screen prompts.

The installer will:
- Place the pipeline files in a system folder (`C:\ProgramData\MAHABOCW\pipeline`)
  that you never need to browse into.
- Silently install all required Python packages (this takes several minutes —
  the wizard progress bar will be active; no terminal window appears).
- Download the self-contained Chromium browser component (~300 MB) used to
  navigate the MAHABOCW portal.

A log file is written to `C:\ProgramData\MAHABOCW\pipeline\install.log`. If anything
goes wrong during installation, share that file when asking for help.

> **If you see a message that Python was not found:** install Python 3.12 or 3.13 from
> https://www.python.org/downloads/ (tick "Add Python to PATH"), then re-run
> MAHABOCW-Pipeline-Setup.exe.

## Step 2 — Install and set up the local AI model

1. Download and install Ollama from https://ollama.com/download
2. Once installed, open a new Command Prompt and run:
   ```
   ollama pull qwen2.5:7b-instruct
   ```
   This downloads roughly 4.7 GB and may take a while depending on your
   internet connection. Let it finish completely before continuing.

## Step 3 — Install the MAHABOCW Verification Tool

Run the installer (`MAHABOCW-GUI-Setup.exe`) provided alongside this document,
and follow the on-screen prompts. A shortcut will be created on your Desktop
and in your Start Menu.

## Step 4 — Configure and run

1. Launch **MAHABOCW Verification Tool** from the Desktop or Start Menu.
2. On the Settings screen, fill in:
   - **Pipeline Folder** — automatically pre-filled if Step 1 completed
     successfully; if it is blank, browse to `C:\ProgramData\MAHABOCW\pipeline`
   - **Input Excel File** — the claims spreadsheet you want to process
   - **Sheet Name** — select from the dropdown once the input file is chosen
   - **Output Excel File** — where the corrected results should be saved
   - **Gemini API Key** — paste your key here
   - **Python Interpreter** — leave as `python` unless Python was not added to
     PATH, in which case browse to your `python.exe` directly
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
| The browser window doesn't open | Make sure Step 1 completed successfully; check `C:\ProgramData\MAHABOCW\pipeline\install.log` for errors and re-run MAHABOCW-Pipeline-Setup.exe if needed. |
| A message about the AI model or Ollama appears | Make sure Ollama is installed and that `ollama pull qwen2.5:7b-instruct` finished completely (Step 2). |
| Pipeline Folder field is blank after first launch | Browse to `C:\ProgramData\MAHABOCW\pipeline` — this means Step 1 was not yet completed or verify_colleges.py is missing from that folder. |
| pip install failed / package errors | Open `C:\ProgramData\MAHABOCW\pipeline\install.log`, look for the failing package, and share that file when asking for help. |
| The tool won't start / interpreter errors | Use the **Test** button next to the Python Interpreter field in Settings to confirm the path is correct. |
| Something else goes wrong mid-run | Click **Open Latest Log File** on the completion screen (or check the `logs` folder inside the pipeline folder) for full details, and share that file when asking for help. |

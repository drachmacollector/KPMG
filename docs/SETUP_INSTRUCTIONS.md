# MAHABOCW Verification Tool — Setup Instructions

Do this once. After that, you only need **Step 3** each time.

## What you need

- Windows 10 or 11, 64-bit
- 16 GB of RAM or more (the tool runs an AI model on this computer)
- About 15 GB of free disk space
- An internet connection during setup and during each run
- Administrator rights for the installation
- Your Gemini API key

You do **not** need to install Python. The installer brings everything it needs.

## Step 1 — Install the tool

1. Run **MAHABOCW-Setup.exe** and follow the prompts.
2. On the **Hardware Acceleration** page, keep **Standard (CPU)** unless this computer has an NVIDIA graphics card.
3. The last part of the installation downloads components (about 1 GB). It can take 10–20 minutes, and the progress bar keeps moving while it works.

If an older MAHABOCW version is installed (the two separate "Pipeline" and "GUI" installers), it is removed automatically. You may need to enter your settings again.

If the installer reports a problem, check your internet connection. Then, from the Start menu, right-click **Repair MAHABOCW components** and choose **Run as administrator**. The details are in `C:\Program Files\MAHABOCW\install.log`; share that file when asking for help.

## Step 2 — Set up the AI model (first launch)

1. Open **MAHABOCW Verification Tool** from the Desktop or the Start menu and click **Get started**.
2. The **System check** at the top of the screen shows what is ready:
   - **Ollama — Not installed:** click **Download Ollama**, install it, then click **Check again**.
   - **Ollama — Installed but not running:** click **Start Ollama**.
   - **AI model — Not downloaded:** click **Download model**. This is about 4.7 GB, and progress is shown in the app. Keep the window open until it finishes.
3. When every item has a green dot, you are ready.

## Step 3 — Run

1. In **Set up a run**, fill in:
   - **Claims workbook (input):** the Excel file with the claims. It is never changed.
   - **Sheet:** chosen from the list.
   - **Results workbook (output):** where the results are saved. Choose an existing results file to continue an earlier run.
   - **Gemini API key** (and optionally an OpenRouter key).
   - **Rows:** all rows, or a range (use Excel's row numbers; row 2 is the first claim).
2. Click **Save & start**.
3. A browser window opens. In that window:
   1. Log in to the MAHABOCW portal, including the captcha.
   2. Open the **Claims** section and bring the **Acknowledgement Number** column into view.
   3. Open that column's menu (☰), click the funnel, and leave the filter box open.
4. Go back to the tool and click **Done — start processing**.
5. The tool now works through the claims on its own. You can **Pause** at any time, or **Stop**. Stop can wait for the current claim to finish, or stop immediately. Every finished claim is already saved, so the next run continues where this one stopped.
6. When it finishes, the summary shows how many claims were verified, how many need manual review, and how many failed. Click **Open results in Excel**. In the results file, filter the `manual_review` column for **YES** to see the claims that need checking.

### Result columns

| Column | Meaning |
| --- | --- |
| `corrected_college_name` / `corrected_college_address` | The verified college name and address |
| `accuracy` | Confidence score, 0–100% |
| `manual_review` | `YES` = please check this claim by hand |
| `online_verification_status` | `VERIFIED`; `FAILED` (college could not be confirmed online); `NO_DOCS` (no usable bonafide or ID); `ERROR` (portal or processing problem — retried on the next run) |

To re-try `FAILED` and `NO_DOCS` claims, tick **Try failed claims again** before starting.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| "Output Excel file is currently open" keeps appearing | Close the results file in Excel. The tool retries every few seconds. |
| A System check item stays red | Click the button next to it, then **Check again**. For "Python packages" or "Chromium browser", run **Repair MAHABOCW components** as administrator. |
| Many claims show `ERROR` | The portal filter may not be set up correctly. Stop the run, check step 3.3 in the browser, and run again (`ERROR` claims are retried). |
| The run stops right away with "could not start" | The message lists what is missing (usually Ollama is not running, or the API key is missing). |
| Anything else | Click **Log file** (on the Run or Done screen) and share that file when asking for help. |

Downloaded claim documents are deleted after each claim by default, because they contain Aadhaar and ration-card details. Logs and the college cache are kept in `%LOCALAPPDATA%\MAHABOCW`.

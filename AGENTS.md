# AGENTS.md

Instructions for AI coding assistants (Claude, Copilot, Cursor, etc.) working in this repository. Read this before making changes.

## What this project is

This is an intelligent document-processing pipeline that automates college name/address verification for MAHABOCW medical scholarship claims:

Playwright portal automation → document download → PaddleOCR → Qwen (Ollama) extraction → Gemini web-grounded resolution → Excel output.

A pywebview + React desktop app (`gui/`) runs the pipeline. One installer ships the app, a private Python 3.12 runtime and the pipeline. Full detail is in `docs/ARCHITECTURE.md`; a short overview is in `README.md`.

## Required reading before non-trivial changes

1. `README.md` — purpose, high-level flow and setup.
2. `docs/ARCHITECTURE.md` — the authoritative technical description. Part A covers the pipeline stage by stage; Part B covers the desktop app, bridge API, event protocol and installer.

Do not guess pipeline behaviour from filenames alone. Read the relevant section of `docs/ARCHITECTURE.md` and the relevant source file before editing.

## Documentation update rule (mandatory)

This repo treats documentation as part of the change, not an afterthought:

- **After any architectural change, update `docs/ARCHITECTURE.md` in the same change.** Architectural changes include:
  - a new or removed pipeline stage,
  - a changed model or provider (e.g. the Gemini model list, OCR engine or extraction model),
  - a changed fallback order,
  - a changed threshold or scoring formula,
  - a new external dependency or service,
  - a change to a file's responsibility, the event protocol or the bridge API,
  - a packaging change,
  - a changed data flow.

  Also update the Mermaid diagrams in `docs/ARCHITECTURE.md` (and in `README.md` if the high-level flow changed) so they still match reality.
- **After any major change** to setup steps, run instructions, repository layout or the overall purpose of the project, **update `README.md`** so it stays accurate and concise. Do not let the README grow into a full technical reference; that belongs in `docs/ARCHITECTURE.md`. End-user steps belong in `docs/SETUP_INSTRUCTIONS.md`.
- If you are unsure whether a change is "architectural" or "major", update the docs anyway. A change is architectural if it would make a paragraph or diagram edge in `docs/ARCHITECTURE.md` factually wrong.
- Never describe planned or aspirational behaviour as current in either file. If code exists but is unused, say so explicitly.

## Code map (see `docs/ARCHITECTURE.md` for full detail)

| File | Responsibility |
| --- | --- |
| `verify_colleges.py` | Orchestrator: preflight, Excel I/O, Playwright automation (with the filtered-grid guard), phase control, statuses, atomic output writes, events. |
| `scoring.py` | `compute_accuracy()`: pure, unit-tested. |
| `document_processor.py` | PDF/image → normalized PNG, type sniffing, hashing, orientation correction. |
| `ocr_engine.py` | PaddleOCR init (GPU only when a device is present) and `ocr_image()`. |
| `extractor.py` | Ollama/Qwen classification + structured extraction (JSON mode), Ollama preflight. |
| `web_resolver.py` | Institution resolution: cache → Gemini (native search grounding) → OpenRouter fallback. |
| `logger_config.py` | Logging, plus `emit_event()` for the `@@MAHABOCW` event stream. |
| `gui/app/` | Desktop backend: `main.py`, `api.py` (JS bridge), `runner.py` (subprocess), `settings.py`. |
| `gui/frontend/` | React/Tailwind UI (built into `gui/frontend_dist/`). |
| `gui/packaging/` | PyInstaller spec, `mahabocw_setup.iss`, `setup_runtime.cmd`, `build.ps1`. |
| `tests/` | pytest suite. |

Untracked or local-only (gitignored): `.env`, `downloads/`, `logs/`, `testing/`, `institution_cache.json`, `gui/frontend_dist/`, `gui/build/`, `gui/dist/`, `gui/packaging/build/`, `gui/packaging/Output/`.

## Conventions and constraints to respect

- **Don't silently change fallback chains or thresholds.** The constants are:
  - `web_resolver.py`: `CACHE_HIT_THRESHOLD`, `CONFIDENCE_REJECT_THRESHOLD`, and the order of `GEMINI_MODELS`;
  - `verify_colleges.py`: `ACCURACY_THRESHOLD`;
  - `scoring.py`: `NAME_AGREEMENT_THRESHOLD`.

  If you change one, update `docs/ARCHITECTURE.md` §A2 (Stage 6/7) to match.
- **Preserve the two-phase document strategy** (Phase 1 fast path, Phase 2 fallback). It exists to control OCR, LLM and API cost.
- **Preserve resumability.** Rows with a final `online_verification_status` (`VERIFIED`, `FAILED`, `NO_DOCS`) or a filled `corrected_college_name` are skipped. `ERROR` rows are retried. Output is saved atomically after every claim.
- **The event protocol is a contract** between `verify_colleges.py` and `gui/app/runner.py`. Change both sides together and update the tables in `docs/ARCHITECTURE.md`.
- **Dependencies:** the pipeline targets **Python 3.12**. Paddle is installed with `--no-deps` from `requirements-paddle-*.txt` (see the header of `requirements-lock.txt`). Never put `paddlepaddle` back into `requirements-lock.txt`.
- **Windows-first setup:** install and run commands are PowerShell.
- **Secrets:** never hardcode `GEMINI_API_KEY` or `OPENROUTER_API_KEY`. For command-line runs they come from `.env`; in the app they are stored with DPAPI encryption and passed as environment variables. Never commit `.env`, `institution_cache.json`, `downloads/` or `logs/`.
- **Manual portal steps stay manual.** Do not automate MAHABOCW login or the captcha.

## Building the desktop app and installer

Use the build script. It runs every step in the right order and refuses to package a stale frontend:

```powershell
powershell -ExecutionPolicy Bypass -File gui\packaging\build.ps1 -Python <python with gui\requirements.txt>
```

The steps are:
1. `npm ci && npm run build`, which writes `gui/frontend_dist/`.
2. A staleness check.
3. PyInstaller.
4. Download and checksum-verify the private Python 3.12 runtime.
5. Inno Setup, producing `gui/packaging/Output/MAHABOCW-Setup.exe`.

Requirements: Node.js 20 LTS or later, and Inno Setup 6 or 7.

## When you finish a change

1. Run `python -m pytest tests` and, for frontend changes, `npm run lint && npm run build` in `gui/frontend`.
2. Re-read the parts of `docs/ARCHITECTURE.md` your change touches. Fix any text, tables, thresholds or diagram nodes and edges that are now inaccurate.
3. If the change affects what a user needs to know to set up, run or understand the project at a glance, update `README.md` (keep it concise) and/or `docs/SETUP_INSTRUCTIONS.md`.
4. Mention in your summary or PR description which docs you updated and why.

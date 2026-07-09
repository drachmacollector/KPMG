# AGENTS.md

Instructions for AI coding assistants (Claude, Copilot, Cursor, etc.) working in this repository. Read this before making changes.

## What this project is

An intelligent document processing pipeline that automates college-name/address verification for MAHABOCW medical scholarship claims: Playwright portal automation → document download → PaddleOCR → Qwen (Ollama) extraction → Gemini web-grounded resolution → Excel output. Full detail lives in `ARCHITECTURE.md`; a short overview lives in `README.md`.

## Required reading before non-trivial changes

1. `README.md` — purpose, high-level flow, setup.
2. `ARCHITECTURE.md` — the authoritative, stage-by-stage technical description of the whole pipeline.

Do not guess at pipeline behavior from filenames alone. Read the relevant stage in `ARCHITECTURE.md` and the relevant source file before editing.

## Documentation update rule (mandatory)

This repo treats documentation as part of the change, not an afterthought:

- **After any architectural change** — a new/removed pipeline stage, a changed model or provider (e.g. Gemini model list, OCR engine, extraction model), a changed fallback order, a changed threshold or scoring formula, a new external dependency/service, a changed file's responsibility, or a changed data flow — **update `ARCHITECTURE.md` in the same change**. Update the Mermaid diagram in `ARCHITECTURE.md` (and in `README.md` if the high-level flow changed) so it still matches reality.
- **After any major change** to setup steps, run instructions, repository layout, or the overall purpose of the project — **update `README.md`** so it stays accurate and concise. Do not let the README regrow into a full technical reference; that belongs in `ARCHITECTURE.md`.
- If you are unsure whether a change is "architectural" or "major," err on the side of updating the docs. A change is architectural if it would make a paragraph or diagram edge in `ARCHITECTURE.md` factually wrong.
- Never describe planned/aspirational behavior as current in either file. If code exists but is unused (e.g. dead code paths), say so explicitly, as `ARCHITECTURE.md` already does for the legacy SerpApi path.

## Code map (see `ARCHITECTURE.md` §2 for full detail)

| File | Responsibility |
| --- | --- |
| `verify_colleges.py` | Orchestrator: Excel I/O, Playwright automation, phase control, accuracy scoring, output writes. |
| `document_processor.py` | PDF/image → normalized PNG, hashing, orientation correction. |
| `ocr_engine.py` | PaddleOCR init and `ocr_image()`. |
| `extractor.py` | Ollama/Qwen document classification + structured extraction. |
| `web_resolver.py` | Institution resolution: cache → Gemini (native search grounding) → OpenRouter fallback. |

Untracked/local-only (gitignored): `.env`, `downloads/`, `logs/`, `testing/`, `institution_cache.json`.
Note: `institution_cache.json` is a runtime-mutating file (added to `.gitignore` to avoid shipping the dev cache as the client's starting state). `logger_config.py` is tracked in the repo.

## Conventions and constraints to respect

- **Don't silently change fallback chains or thresholds.** `web_resolver.py` has explicit constants (`CACHE_HIT_THRESHOLD`, `CONFIDENCE_REJECT_THRESHOLD`, `GEMINI_MODELS` order) and `verify_colleges.py` has `ACCURACY_THRESHOLD`. If you change one, update `ARCHITECTURE.md` §2 (Stage 6/7) and §5 to match.
- **Preserve the two-phase document strategy** (Phase 1 fast path, Phase 2 fallback) — it exists to control OCR/LLM/API cost. Don't collapse it into a single pass without discussion.
- **Preserve resumability**: the script skips rows where `corrected_college_name` is already populated and saves after every claim. Don't remove this without very good reason — long-running claim batches depend on it.
- **Windows-first setup**: install/run commands in `README.md` are PowerShell. Keep new setup steps consistent with that unless explicitly asked to add cross-platform instructions.
- **Secrets**: never hardcode `GEMINI_API_KEY` or `OPENROUTER_API_KEY`; they come from `.env` via `dotenv`. Never commit `.env`, `institution_cache.json`, `downloads/`, or `logs/`.
- **Manual portal steps stay manual.** Do not attempt to automate MAHABOCW login/captcha; the pipeline is intentionally semi-automated.

## When you finish a change

1. Re-read the parts of `ARCHITECTURE.md` your change touches; fix any now-inaccurate text, tables, thresholds, or diagram nodes/edges.
2. If the change affects what a user needs to know to set up, run, or understand the project at a glance, update `README.md` accordingly — keep it concise; move detail into `ARCHITECTURE.md` instead of expanding the README.
3. Mention in your summary/PR description which docs you updated and why.

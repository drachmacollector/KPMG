"""
app/api.py

Api — the sole bridge surface between the React frontend and the Python backend.
Every public method is callable from React via window.pywebview.api.method(...)
(wrapped by gui/frontend/src/lib/bridge.js).

  PULL      get_initial_state, get_sheet_names, test_python, system_check
  DIALOG    pick_pipeline_folder, pick_input_file, pick_output_file, pick_python_exe
  COMMAND   save_settings, start_pipeline, pause_pipeline, resume_pipeline,
            stop_pipeline (graceful), force_stop_pipeline, cancel_pipeline (alias),
            confirm_login, open_file, open_log, open_folder, open_url,
            start_ollama, pull_model
  PUSH      push_log, push_event, push_progress, push_done, push_error,
            push_awaiting_login, model-pull progress

Push payloads are JSON → UTF-8 → base64 and delivered with evaluate_js() as
CustomEvents; the JS side decodes with TextDecoder so Devanagari text survives.
"""
from __future__ import annotations

import base64
import glob
import json
import os
import subprocess
import threading
import urllib.request
import webbrowser
from typing import Optional

import openpyxl
import webview

from app.runner import PipelineRunner
from app.settings import (
    DATA_DIR,
    Settings,
    environment_info,
    load_settings,
    save_settings,
)

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5:7b-instruct"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/windows"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Run inside the pipeline's Python to check packages, Chromium and GPU.
_RUNTIME_CHECK = r"""
import json, os, sys
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
out = {"python": sys.version.split()[0], "missing": [], "chromium": "", "gpu": ""}
for mod in ("pandas", "openpyxl", "playwright", "bs4", "fitz", "cv2", "PIL", "ollama",
            "paddle", "paddleocr", "google.genai", "rapidfuzz", "dotenv", "tqdm"):
    try:
        __import__(mod)
    except Exception as e:
        out["missing"].append(f"{mod} ({type(e).__name__})")
try:
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    path = p.chromium.executable_path
    p.stop()
    out["chromium"] = path if os.path.exists(path) else ""
except Exception:
    pass
try:
    import paddle
    if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
        out["gpu"] = paddle.device.cuda.get_device_name(0)
except Exception:
    pass
print("@@CHECK " + json.dumps(out))
"""


def _count_input_rows(settings_dict: dict) -> Optional[int]:
    """Rows that will be processed (None if unknown)."""
    try:
        wb = openpyxl.load_workbook(settings_dict.get("input_file", ""), read_only=True)
        ws = wb[settings_dict.get("sheet_name", "")]
        sheet_data_rows = max((ws.max_row or 1) - 1, 0)
        wb.close()

        if settings_dict.get("process_mode") == "range":
            try:
                start = int(settings_dict.get("start_row", 0))
                end = int(settings_dict.get("end_row", 0))
                range_count = max(end - start + 1, 0)
                return min(range_count, sheet_data_rows) or None
            except (ValueError, TypeError):
                pass

        return sheet_data_rows or None
    except Exception:
        return None


def _ollama_get(path: str, timeout: float = 3.0):
    with urllib.request.urlopen(OLLAMA_URL + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ollama_app_exe() -> str:
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama app.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama app.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return ""


class Api:
    """JS bridge surface exposed as window.pywebview.api in the React frontend."""

    def __init__(self) -> None:
        self._window: Optional[webview.Window] = None
        self._runner: Optional[PipelineRunner] = None
        self._pull_thread: Optional[threading.Thread] = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    # ------------------------------------------------------------------
    # PULL
    # ------------------------------------------------------------------

    def get_initial_state(self) -> dict:
        return {
            "settings": load_settings(),
            "environment": environment_info(),
            "running": self.is_running(),
        }

    def is_running(self) -> bool:
        return bool(self._runner and self._runner.is_alive)

    def get_sheet_names(self, file_path: str) -> list:
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True)
            names = wb.sheetnames
            wb.close()
            return names
        except Exception:
            return []

    def test_python(self, exe: str) -> dict:
        """Run `exe --version`; only a zero exit code counts as success."""
        exe = (exe or "").strip() or Settings().effective_python_exe()
        try:
            result = subprocess.run(
                [exe, "--version"], capture_output=True, text=True, timeout=15,
                creationflags=_CREATE_NO_WINDOW,
            )
            version = (result.stdout.strip() or result.stderr.strip())
            if result.returncode != 0 or not version.lower().startswith("python"):
                return {"ok": False, "version": "", "error": f"Not a working Python interpreter: {exe}"}
            return {"ok": True, "version": version, "error": ""}
        except FileNotFoundError:
            return {"ok": False, "version": "", "error": f"Interpreter not found: {exe}"}
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"ok": False, "version": "", "error": str(exc) or "Timed out"}

    def system_check(self, settings: Optional[dict] = None) -> dict:
        """
        Check everything a run needs.  Each item:
            {id, label, status: ok|warn|error, detail, action?}
        `blocking` is True when any item has status "error".
        """
        s = Settings.from_dict(settings or load_settings())
        items = []

        # 1. Pipeline files
        script = os.path.join(s.effective_pipeline_dir(), "verify_colleges.py")
        if os.path.isfile(script):
            items.append({"id": "pipeline", "label": "Pipeline files", "status": "ok", "detail": s.effective_pipeline_dir()})
        else:
            items.append({"id": "pipeline", "label": "Pipeline files", "status": "error",
                          "detail": "verify_colleges.py not found. Reinstall MAHABOCW."})

        # 2. Python runtime, packages, Chromium, GPU (one subprocess)
        python_exe = s.effective_python_exe()
        check = None
        try:
            env = os.environ.copy()
            env.update({k: v for k, v in s.build_env_overrides().items() if k == "PLAYWRIGHT_BROWSERS_PATH"})
            proc = subprocess.run(
                [python_exe, "-c", _RUNTIME_CHECK], capture_output=True, text=True,
                timeout=180, env=env, creationflags=_CREATE_NO_WINDOW,
            )
            for line in proc.stdout.splitlines():
                if line.startswith("@@CHECK "):
                    check = json.loads(line[len("@@CHECK "):])
        except Exception as exc:
            items.append({"id": "runtime", "label": "Python runtime", "status": "error",
                          "detail": f"Could not run {python_exe}: {exc}"})
        if check is not None:
            if check["missing"]:
                items.append({"id": "runtime", "label": "Python packages", "status": "error",
                              "detail": "Missing: " + ", ".join(check["missing"]) + ". Re-run the installer (Repair)."})
            else:
                items.append({"id": "runtime", "label": "Python packages", "status": "ok",
                              "detail": f"Python {check['python']}"})
            if check["chromium"]:
                items.append({"id": "chromium", "label": "Chromium browser", "status": "ok", "detail": "Installed"})
            else:
                items.append({"id": "chromium", "label": "Chromium browser", "status": "error",
                              "detail": "Not installed. Re-run the installer (Repair)."})
            items.append({"id": "gpu", "label": "OCR acceleration", "status": "ok",
                          "detail": f"GPU: {check['gpu']}" if check["gpu"] else "CPU (slower, but works)"})
        elif not any(i["id"] == "runtime" for i in items):
            items.append({"id": "runtime", "label": "Python runtime", "status": "error",
                          "detail": f"{python_exe} did not respond as expected."})

        # 3. Ollama + model
        try:
            tags = _ollama_get("/api/tags")
            names = {m.get("name") or m.get("model") for m in tags.get("models", [])}
            if OLLAMA_MODEL in names or f"{OLLAMA_MODEL}:latest" in names:
                items.append({"id": "model", "label": "AI model (Qwen 2.5 7B)", "status": "ok", "detail": "Ready"})
            else:
                items.append({"id": "model", "label": "AI model (Qwen 2.5 7B)", "status": "error",
                              "detail": "Not downloaded yet (~4.7 GB).", "action": "pull_model"})
            items.insert(len(items) - 1, {"id": "ollama", "label": "Ollama", "status": "ok", "detail": "Running"})
        except Exception:
            if _ollama_app_exe():
                items.append({"id": "ollama", "label": "Ollama", "status": "error",
                              "detail": "Installed but not running.", "action": "start_ollama"})
            else:
                items.append({"id": "ollama", "label": "Ollama", "status": "error",
                              "detail": "Not installed. Download and install it, then re-check.", "action": "install_ollama"})

        # 4. API key
        if s.gemini_api_key.strip():
            items.append({"id": "gemini", "label": "Gemini API key", "status": "ok", "detail": "Set"})
        else:
            items.append({"id": "gemini", "label": "Gemini API key", "status": "error", "detail": "Enter your key below."})

        return {"items": items, "blocking": any(i["status"] == "error" for i in items)}

    # ------------------------------------------------------------------
    # DIALOGS
    # ------------------------------------------------------------------

    @staticmethod
    def _first(result):
        if result:
            return result[0] if isinstance(result, (list, tuple)) else result
        return None

    def pick_pipeline_folder(self) -> Optional[str]:
        return self._first(self._window.create_file_dialog(webview.FOLDER_DIALOG))

    def pick_input_file(self) -> Optional[str]:
        return self._first(self._window.create_file_dialog(
            webview.OPEN_DIALOG, file_types=("Excel Files (*.xlsx;*.xls)", "All Files (*.*)")))

    def pick_output_file(self) -> Optional[str]:
        path = self._first(self._window.create_file_dialog(
            webview.SAVE_DIALOG, file_types=("Excel Files (*.xlsx)", "All Files (*.*)")))
        if path and not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        return path

    def pick_python_exe(self) -> Optional[str]:
        return self._first(self._window.create_file_dialog(
            webview.OPEN_DIALOG, file_types=("Executables (*.exe)", "All Files (*.*)")))

    # ------------------------------------------------------------------
    # COMMANDS
    # ------------------------------------------------------------------

    def save_settings(self, settings: dict) -> dict:
        save_settings(settings)
        return {"ok": True}

    def start_pipeline(self, settings: dict) -> dict:
        if self.is_running():
            return {"ok": False, "error": "A run is already in progress.", "total_rows": None}
        save_settings(settings)
        total_rows = _count_input_rows(settings)
        enriched = dict(settings)
        enriched["_total_rows_hint"] = total_rows
        self._runner = PipelineRunner(api_ref=self, settings=enriched)
        self._runner.start()
        return {"ok": True, "total_rows": total_rows}

    def pause_pipeline(self) -> None:
        if self._runner:
            self._runner.pause()

    def resume_pipeline(self) -> None:
        if self._runner:
            self._runner.resume()

    def stop_pipeline(self) -> None:
        """Finish the current claim, save, then stop."""
        if self._runner:
            self._runner.stop()

    def force_stop_pipeline(self) -> None:
        if self._runner:
            self._runner.force_stop()

    def cancel_pipeline(self) -> None:
        self.force_stop_pipeline()

    def confirm_login(self) -> None:
        if self._runner:
            self._runner.confirm_login()

    def open_file(self, path: str) -> None:
        if path and os.path.isfile(path):
            os.startfile(path)

    def open_folder(self, which: str = "data") -> None:
        target = {"data": DATA_DIR, "downloads": os.path.join(DATA_DIR, "downloads"),
                  "logs": os.path.join(DATA_DIR, "logs")}.get(which, DATA_DIR)
        os.makedirs(target, exist_ok=True)
        os.startfile(target)

    def open_log(self, _pipeline_dir: str = "") -> None:
        """Open the most recent .log file from the data folder's logs/."""
        log_files = glob.glob(os.path.join(DATA_DIR, "logs", "*.log"))
        if log_files:
            os.startfile(max(log_files, key=os.path.getmtime))

    def open_url(self, url: str) -> None:
        if url in (OLLAMA_DOWNLOAD_URL, "https://aistudio.google.com/apikey"):
            webbrowser.open(url)

    def install_ollama(self) -> None:
        webbrowser.open(OLLAMA_DOWNLOAD_URL)

    def start_ollama(self) -> dict:
        exe = _ollama_app_exe()
        if not exe:
            return {"ok": False}
        subprocess.Popen([exe], creationflags=_CREATE_NO_WINDOW)
        return {"ok": True}

    def pull_model(self) -> dict:
        """Download the Qwen model through the Ollama API, streaming progress."""
        if self._pull_thread and self._pull_thread.is_alive():
            return {"ok": True, "already_running": True}

        def worker():
            try:
                req = urllib.request.Request(
                    OLLAMA_URL + "/api/pull",
                    data=json.dumps({"model": OLLAMA_MODEL, "stream": True}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    for raw in resp:
                        if not raw.strip():
                            continue
                        msg = json.loads(raw.decode("utf-8"))
                        if msg.get("error"):
                            raise RuntimeError(msg["error"])
                        self._dispatch("model-pull", {
                            "status": msg.get("status", ""),
                            "completed": msg.get("completed"),
                            "total": msg.get("total"),
                            "done": msg.get("status") == "success",
                        })
            except Exception as exc:
                self._dispatch("model-pull", {"status": "error", "error": str(exc), "done": True})

        self._pull_thread = threading.Thread(target=worker, daemon=True)
        self._pull_thread.start()
        return {"ok": True}

    # ------------------------------------------------------------------
    # PUSH — called by PipelineRunner from its background threads
    # ------------------------------------------------------------------

    def push_log(self, payload: dict) -> None:
        self._dispatch("pipeline-log", payload)

    def push_event(self, payload: dict) -> None:
        self._dispatch("pipeline-event", payload)

    def push_progress(self, payload: dict) -> None:
        self._dispatch("pipeline-progress", payload)

    def push_done(self, payload: dict) -> None:
        self._dispatch("pipeline-done", payload)

    def push_error(self, payload: dict) -> None:
        self._dispatch("pipeline-error", payload)

    def push_awaiting_login(self) -> None:
        self._dispatch("pipeline-awaiting-login", {})

    def _dispatch(self, event_name: str, payload: dict) -> None:
        if not self._window:
            return
        json_str = json.dumps(payload, ensure_ascii=False)
        b64_str = base64.b64encode(json_str.encode("utf-8")).decode("ascii")
        js = (
            "(function(){var b='" + b64_str + "';"
            "var u=Uint8Array.from(atob(b),function(c){return c.charCodeAt(0);});"
            "var d=JSON.parse(new TextDecoder('utf-8').decode(u));"
            "window.dispatchEvent(new CustomEvent('" + event_name + "',{detail:d}));})();"
        )
        try:
            self._window.evaluate_js(js)
        except Exception:
            pass

"""
app/settings.py

Settings dataclass + JSON persistence + install-layout detection for the
MAHABOCW GUI.

Stored at: %APPDATA%\\MAHABOCW-GUI\\settings.json
API keys are encrypted with Windows DPAPI (bound to the current Windows user).

Install layout written by MAHABOCW-Setup.exe ({autopf}\\MAHABOCW):
    app\\mahabocw_gui.exe     this GUI (PyInstaller onedir)
    pipeline\\                verify_colleges.py and friends
    runtime\\python.exe       private Python 3.12 with the pipeline packages
    browsers\\                Playwright Chromium (PLAYWRIGHT_BROWSERS_PATH)

Runtime data (downloads, logs, institution cache) lives in a per-user,
writable data folder: %LOCALAPPDATA%\\MAHABOCW.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import asdict, dataclass, fields


CONFIG_DIR: str = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "MAHABOCW-GUI",
)
CONFIG_PATH: str = os.path.join(CONFIG_DIR, "settings.json")

# Per-user writable working folder for the pipeline subprocess.
DATA_DIR: str = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "MAHABOCW",
)
STOP_FILE: str = os.path.join(DATA_DIR, ".stop_requested")

_SECRET_FIELDS = ("gemini_api_key", "openrouter_api_key")
_DPAPI_PREFIX = "dpapi:"


# ---------------------------------------------------------------------------
# Install layout detection
# ---------------------------------------------------------------------------

def install_root() -> str:
    """Root of a MAHABOCW-Setup.exe install, or "" when not installed that way."""
    if getattr(sys, "frozen", False):
        # {root}\app\mahabocw_gui.exe
        root = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
        if os.path.isfile(os.path.join(root, "pipeline", "verify_colleges.py")):
            return root
    return ""


def default_pipeline_dir() -> str:
    root = install_root()
    if root:
        return os.path.join(root, "pipeline")
    # Development: the repo root (gui/app/settings.py -> repo root).
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.isfile(os.path.join(repo_root, "verify_colleges.py")):
        return repo_root
    return ""


def default_python_exe() -> str:
    root = install_root()
    if root:
        bundled = os.path.join(root, "runtime", "python.exe")
        if os.path.isfile(bundled):
            return bundled
    return "python"


def default_browsers_path() -> str:
    root = install_root()
    if root:
        path = os.path.join(root, "browsers")
        if os.path.isdir(path):
            return path
    return ""


# ---------------------------------------------------------------------------
# DPAPI (Windows) secret protection
# ---------------------------------------------------------------------------

def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def protect_secret(value: str) -> str:
    if not value or os.name != "nt":
        return value
    try:
        return _DPAPI_PREFIX + base64.b64encode(_dpapi(value.encode("utf-8"), True)).decode("ascii")
    except Exception:
        return value


def unprotect_secret(value: str) -> str:
    if not value or not value.startswith(_DPAPI_PREFIX):
        return value or ""
    try:
        return _dpapi(base64.b64decode(value[len(_DPAPI_PREFIX):]), False).decode("utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    """Persisted user configuration for the GUI."""

    # Advanced (developer) overrides.  Empty = detect automatically.
    pipeline_dir: str = ""
    python_exe: str = ""

    # Environment variable pass-throughs to the pipeline.
    input_file: str = ""          # -> MAHABOCW_INPUT_FILE
    sheet_name: str = ""          # -> MAHABOCW_SHEET_NAME
    output_file: str = ""         # -> MAHABOCW_OUTPUT_FILE
    gemini_api_key: str = ""      # -> GEMINI_API_KEY
    openrouter_api_key: str = ""  # -> OPENROUTER_API_KEY (optional fallback)

    # Row processing mode.
    process_mode: str = "all"     # "all" | "range"
    start_row: str = ""
    end_row: str = ""

    # Behaviour toggles.
    delete_downloads: bool = True   # remove claim documents (PII) after each claim
    retry_failed: bool = False      # re-run rows marked FAILED / NO_DOCS

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = asdict(self)
        for key in _SECRET_FIELDS:
            data[key] = protect_secret(data[key])
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, CONFIG_PATH)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Forward-compat: ignore unknown keys, fill missing keys with defaults."""
        valid = {f.name: f for f in fields(cls)}
        kwargs = {}
        for k, v in (data or {}).items():
            if k not in valid:
                continue
            if valid[k].type in ("bool", bool):
                v = bool(v)
            elif v is None:
                v = ""
            else:
                v = str(v)
            kwargs[k] = v
        return cls(**kwargs)

    @classmethod
    def load(cls) -> "Settings":
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                for key in _SECRET_FIELDS:
                    if key in data:
                        data[key] = unprotect_secret(data[key] or "")
                # Settings written by older versions pointed at "python" and at
                # a pipeline folder that may no longer exist; treat both as
                # "detect automatically".
                if data.get("python_exe") == "python":
                    data["python_exe"] = ""
                stored_dir = data.get("pipeline_dir") or ""
                if stored_dir and not os.path.isfile(os.path.join(stored_dir, "verify_colleges.py")):
                    data["pipeline_dir"] = ""
                return cls.from_dict(data)
            except (json.JSONDecodeError, TypeError, OSError):
                pass
        return cls()

    # -- effective values ------------------------------------------------

    def effective_pipeline_dir(self) -> str:
        return self.pipeline_dir.strip() or default_pipeline_dir()

    def effective_python_exe(self) -> str:
        return self.python_exe.strip() or default_python_exe()

    def build_env_overrides(self) -> dict[str, str]:
        """Build the env var dict to pass to the pipeline subprocess."""
        overrides: dict[str, str] = {
            "MAHABOCW_INPUT_FILE": self.input_file,
            "MAHABOCW_SHEET_NAME": self.sheet_name,
            "MAHABOCW_OUTPUT_FILE": self.output_file,
            "MAHABOCW_STOP_FILE": STOP_FILE,
            "MAHABOCW_DELETE_DOWNLOADS": "true" if self.delete_downloads else "false",
            "MAHABOCW_RETRY_FAILED": "true" if self.retry_failed else "false",
            "PYTHONIOENCODING": "utf-8",
        }
        if self.gemini_api_key:
            overrides["GEMINI_API_KEY"] = self.gemini_api_key
        if self.openrouter_api_key:
            overrides["OPENROUTER_API_KEY"] = self.openrouter_api_key

        browsers = default_browsers_path()
        if browsers:
            overrides["PLAYWRIGHT_BROWSERS_PATH"] = browsers

        if self.process_mode == "all":
            overrides["EXCEL_PROCESS_ALL"] = "true"
        else:
            overrides["EXCEL_PROCESS_ALL"] = "false"
            if self.start_row:
                overrides["EXCEL_START_ROW"] = self.start_row
            if self.end_row:
                overrides["EXCEL_END_ROW"] = self.end_row

        return overrides


# ---------------------------------------------------------------------------
# Module-level helpers for api.py (JS bridge works with plain dicts)
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    return asdict(Settings.load())


def save_settings(data: dict) -> None:
    Settings.from_dict(data).save()


def environment_info() -> dict:
    """Detected paths, shown read-only in the Advanced section."""
    return {
        "install_root": install_root(),
        "default_pipeline_dir": default_pipeline_dir(),
        "default_python_exe": default_python_exe(),
        "browsers_path": default_browsers_path(),
        "data_dir": DATA_DIR,
    }

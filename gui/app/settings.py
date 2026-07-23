"""
app/settings.py

Settings dataclass + JSON persistence for the MAHABOCW GUI.

Stored at: %APPDATA%\\MAHABOCW-GUI\\settings.json
Never written inside the pipeline repo directory.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field


CONFIG_DIR: str = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "MAHABOCW-GUI",
)
CONFIG_PATH: str = os.path.join(CONFIG_DIR, "settings.json")

# Fixed install location written by MAHABOCW-Pipeline-Setup.exe.
# C:\ProgramData is {commonappdata} in Inno Setup — a system folder that
# non-technical users are unlikely to browse into casually.
PIPELINE_INSTALL_DIR: str = r"C:\ProgramData\MAHABOCW\pipeline"


def default_pipeline_dir() -> str:
    """Return the standard pipeline install path if verify_colleges.py is there.

    Used by Settings.load() to pre-fill the Pipeline Folder on first launch
    after MAHABOCW-Pipeline-Setup.exe has been run.  Returns "" if the
    pipeline has not been installed at the expected location.
    """
    sentinel = os.path.join(PIPELINE_INSTALL_DIR, "verify_colleges.py")
    return PIPELINE_INSTALL_DIR if os.path.isfile(sentinel) else ""


@dataclass
class Settings:
    """Persisted user configuration for the GUI."""

    # Path to the cloned pipeline repo root (where verify_colleges.py lives).
    pipeline_dir: str = ""

    # Python interpreter used to launch verify_colleges.py.
    # Defaults to "python" (resolved via PATH).
    python_exe: str = "python"

    # Environment variable pass-throughs to the pipeline.
    input_file: str = ""    # -> MAHABOCW_INPUT_FILE
    sheet_name: str = ""    # -> MAHABOCW_SHEET_NAME
    output_file: str = ""   # -> MAHABOCW_OUTPUT_FILE
    gemini_api_key: str = ""  # -> GEMINI_API_KEY

    # Row processing mode passed to pipeline via env vars.
    # "all"  -> EXCEL_PROCESS_ALL=true
    # "range" -> EXCEL_START_ROW / EXCEL_END_ROW set
    process_mode: str = "all"
    start_row: str = ""
    end_row: str = ""

    def save(self) -> None:
        """Persist settings to JSON in the user's APPDATA folder."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from JSON, or return defaults if file missing/corrupt.

        If pipeline_dir is empty after loading (either because settings.json
        doesn't exist yet or the field was never filled in), fall back to
        default_pipeline_dir() so the Settings screen is pre-filled when
        MAHABOCW-Pipeline-Setup.exe has already been run.
        """
        instance: "Settings"
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # Forward-compat: ignore unknown keys, fill missing keys with defaults.
                valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                instance = cls(**filtered)
            except (json.JSONDecodeError, TypeError):
                instance = cls()
        else:
            instance = cls()

        # Auto-detect the standard pipeline location if no dir is configured.
        # This pre-fills the Settings screen without requiring the user to Browse.
        if not instance.pipeline_dir:
            instance.pipeline_dir = default_pipeline_dir()

        return instance

    def is_runnable(self) -> bool:
        """Return True when minimum required fields are filled in."""
        return bool(
            self.pipeline_dir
            and self.python_exe
            and self.input_file
            and self.sheet_name
            and self.output_file
        )

    def build_env_overrides(self) -> dict[str, str]:
        """Build the env var dict to pass to the pipeline subprocess."""
        overrides: dict[str, str] = {
            "MAHABOCW_INPUT_FILE": self.input_file,
            "MAHABOCW_SHEET_NAME": self.sheet_name,
            "MAHABOCW_OUTPUT_FILE": self.output_file,
        }
        if self.gemini_api_key:
            overrides["GEMINI_API_KEY"] = self.gemini_api_key

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
# Module-level helpers for api.py (JS bridge compatibility)
# These accept/return plain dicts so the bridge doesn't need to know about
# the Settings dataclass.
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    """Load persisted settings and return as a plain dict for the JS bridge."""
    return asdict(Settings.load())


def save_settings(data: dict) -> None:
    """Accept a plain dict from the JS bridge and persist it.

    Forward-compat: unknown keys are ignored; missing keys fall back to
    dataclass defaults, matching the same contract as Settings.load().
    """
    valid_keys = {f.name for f in Settings.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    Settings(**filtered).save()

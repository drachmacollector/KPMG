"""
app/runner.py

PipelineRunner — manages the verify_colleges.py subprocess.

Architecture change (pywebview migration):
    Previously subclassed QThread and emitted PySide6 Signals.
    Now uses threading.Thread and calls api.push_*() to dispatch
    CustomEvents to the React frontend via window.evaluate_js().

    Every line of subprocess/psutil logic is preserved exactly.
    Only the base class and the communication points change:

    Old (QThread + Signal):            New (threading.Thread + push):
    ─────────────────────────────────  ───────────────────────────────────────
    self.log_line.emit(line)        →  self.api.push_log({"line": line})
    self.awaiting_login.emit()      →  self.api.push_awaiting_login()
    self.progress.emit(n)           →  self.api.push_progress({"count": n, ...})
    self.finished_ok.emit()         →  self.api.push_done({claims_seen, output})
    self.finished_error.emit(msg)   →  self.api.push_error({"message": msg})
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
from typing import Optional

import psutil

from app.settings import Settings


# The exact substring the pipeline prints before blocking on input().
LOGIN_PROMPT_MARKER = "Press ENTER here"

# Matches the acknowledgement log lines used to track per-claim progress.
# Pipeline source (verify_colleges.py ~line 457):
#   logger.info(f"Acknowledgement: {ack_no}\n")
ACK_LINE_RE = re.compile(r"Acknowledgement:\s*(\S+)")

# Strip ANSI colour/style escape sequences (tqdm emits these; the log pane
# in the React frontend would show them as literal garbage text).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


class PipelineRunner:
    """
    Manages a single run of verify_colleges.py as a subprocess.

    Communication with the React frontend happens via the Api instance:

        api.push_log({"line": str})
            Every stdout/stderr line from the subprocess.

        api.push_awaiting_login()
            Emitted once when the pipeline prints its human-handoff prompt.
            The UI should show the login-confirmation banner.

        api.push_progress({"count": int, "total": int | None})
            Number of claims started so far (driven by Acknowledgement: lines).
            total is None when the row count is not known.

        api.push_done({"claims_seen": int, "output_file": str})
            Subprocess exited with code 0.

        api.push_error({"message": str})
            Subprocess exited with non-zero code, was cancelled, or failed
            to start.
    """

    def __init__(self, api_ref, settings: dict) -> None:
        self.api = api_ref          # reference to the Api instance
        self.settings = settings    # raw dict from the JS bridge

        # Reconstruct typed Settings to reuse build_env_overrides() and
        # access typed fields without repeating dict-key strings everywhere.
        self._typed: Settings = Settings(**{
            k: v for k, v in settings.items()
            if k in Settings.__dataclass_fields__
        })

        # total_rows_hint may be injected by Api.start_pipeline(); defaults None.
        self._total_rows: Optional[int] = settings.get("_total_rows_hint")

        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._claims_seen: int = 0
        self._cancel_requested: bool = False
        self._login_emitted: bool = False

    # ------------------------------------------------------------------
    # Thread management
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the worker on a daemon thread (does not block)."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Worker thread body — runs entirely on the background thread."""
        env = os.environ.copy()
        env.update(self._typed.build_env_overrides())

        # Ensure Python stdout is line-buffered even when piped.
        env["PYTHONUNBUFFERED"] = "1"

        python_exe = self._typed.python_exe or "python"
        pipeline_dir = self._typed.pipeline_dir

        try:
            self._proc = subprocess.Popen(
                [python_exe, "verify_colleges.py"],
                cwd=pipeline_dir,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # merge stderr into stdout
                text=True,
                encoding="utf-8",           # explicit UTF-8 avoids cp1252 mojibake
                errors="replace",           # never crash on undecodable bytes
                bufsize=1,                  # line-buffered
            )
        except FileNotFoundError:
            self.api.push_error({
                "message": (
                    f"Could not find Python interpreter:\n  {python_exe}\n\n"
                    "Check the 'Python Interpreter' path in Settings."
                )
            })
            return
        except Exception as exc:
            self.api.push_error({"message": f"Failed to launch pipeline:\n{exc}"})
            return

        # ----------------------------------------------------------------
        # Character-by-character stdout reader.
        #
        # Why not the simpler "for line in self._proc.stdout"?
        # Python's file iterator only yields a line once it hits \n or EOF.
        # The pipeline's  input("Press ENTER here …")  writes its prompt
        # string WITHOUT a trailing newline — it just sits in the pipe
        # buffer, the iterator never yields it, LOGIN_PROMPT_MARKER never
        # fires, and the "Continue" button never appears.
        #
        # Reading one character at a time lets us check the growing buffer
        # before a newline arrives, so we catch the input() prompt promptly.
        # ----------------------------------------------------------------
        buffer = ""
        while True:
            ch = self._proc.stdout.read(1)
            if ch == "":          # EOF — subprocess closed stdout
                break
            buffer += ch

            if ch in ("\n", "\r"):
                # Completed line — process and reset buffer.
                line = buffer.rstrip("\r\n")
                buffer = ""
                if not line:
                    continue
                self.api.push_log({"line": _strip_ansi(line)})

                # Detect human-in-the-loop pause (emitted only once).
                if not self._login_emitted and LOGIN_PROMPT_MARKER in line:
                    self._login_emitted = True
                    self.api.push_awaiting_login()

                # Track per-claim progress via Acknowledgement: lines.
                if ACK_LINE_RE.search(line):
                    self._claims_seen += 1
                    self.api.push_progress({
                        "count": self._claims_seen,
                        "total": self._total_rows,
                    })
            else:
                # No newline yet — check the in-progress buffer.
                # input()'s prompt will never produce a newline, so this is
                # the only way to catch LOGIN_PROMPT_MARKER in that case.
                if not self._login_emitted and LOGIN_PROMPT_MARKER in buffer:
                    self._login_emitted = True
                    self.api.push_log({"line": _strip_ansi(buffer)})
                    self.api.push_awaiting_login()
                    buffer = ""   # consumed — don't re-emit when \n arrives

        # Flush any partial line left in the buffer at EOF.
        if buffer:
            self.api.push_log({"line": _strip_ansi(buffer)})

        returncode = self._proc.wait()

        if self._cancel_requested:
            self.api.push_error({"message": "Run cancelled by user."})
        elif returncode == 0:
            self.api.push_done({
                "claims_seen": self._claims_seen,
                "output_file": self._typed.output_file,
            })
        else:
            self.api.push_error({
                "message": (
                    f"Pipeline exited with code {returncode}.\n"
                    "Check the log pane above for details."
                )
            })

    # ------------------------------------------------------------------
    # Control methods — safe to call from any thread
    # ------------------------------------------------------------------

    def confirm_login(self) -> None:
        """
        Send a newline to the pipeline's stdin to unblock the input() call.
        Call this when the user clicks 'I've logged in — Continue'.
        """
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write("\n")
                self._proc.stdin.flush()
            except OSError:
                pass

    def pause(self) -> None:
        """Suspend all threads of the pipeline process (Windows: SuspendThread)."""
        if self._proc:
            try:
                psutil.Process(self._proc.pid).suspend()
            except psutil.Error:
                pass

    def resume(self) -> None:
        """Resume a previously suspended pipeline process."""
        if self._proc:
            try:
                psutil.Process(self._proc.pid).resume()
            except psutil.Error:
                pass

    def cancel(self) -> None:
        """
        Request cancellation.  Sets the flag first so push_error carries
        'cancelled' rather than the raw exit code.

        Playwright's Chromium runs as a child process of the pipeline's
        python.exe.  Terminating just the parent abruptly (instead of letting
        the ``with sync_playwright()`` block exit normally) leaves an orphaned
        chrome.exe behind.  Kill the full process tree to avoid accumulating
        zombie browser processes across cancel/resume sessions.
        """
        self._cancel_requested = True
        if self._proc:
            try:
                parent = psutil.Process(self._proc.pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.terminate()
                parent.terminate()
                psutil.wait_procs(children, timeout=3)
            except psutil.Error:
                pass

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def claims_seen(self) -> int:
        return self._claims_seen

    @property
    def is_running_proc(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

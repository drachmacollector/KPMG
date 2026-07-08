"""
app/runner.py

PipelineRunner — the core QThread that owns the verify_colleges.py subprocess.

Design contract:
  - Launched via PipelineRunner.start() from the GUI thread.
  - All Qt signals are emitted from the QThread (safe for cross-thread connections
    with the default Qt::QueuedConnection).
  - The subprocess is communicated with ONLY via:
      env overrides (config in)
      stdout/stderr merged pipe (log + progress out)
      stdin pipe (login confirmation in)
  - psutil is used for suspend/resume/terminate — no pipeline code changes needed.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Optional

import psutil
from PySide6.QtCore import QThread, Signal


# The exact substring the pipeline prints before blocking on input().
LOGIN_PROMPT_MARKER = "Press ENTER here"

# Matches the acknowledgement log lines used to track per-claim progress.
# Pipeline source (verify_colleges.py ~line 457):
#   logger.info(f"Acknowledgement: {ack_no}\n")
ACK_LINE_RE = re.compile(r"Acknowledgement:\s*(\S+)")

# Strip ANSI colour/style escape sequences (tqdm emits these; QPlainTextEdit
# is not a terminal and would show them as literal garbage text).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


class PipelineRunner(QThread):
    """
    Manages a single run of verify_colleges.py as a subprocess.

    Signals
    -------
    log_line(str)
        Every stdout/stderr line from the subprocess (stripped of trailing newline).
    awaiting_login()
        Emitted once when the pipeline prints its human-handoff prompt.
        The UI should show the login-confirmation banner.
    progress(int)
        Number of claims started so far (driven by Acknowledgement: lines).
    finished_ok()
        The subprocess exited with code 0.
    finished_error(str)
        The subprocess exited with non-zero code, was cancelled, or failed
        to start.  The argument is a human-readable error message.
    process_started(int)
        Emitted with the subprocess PID right after Popen succeeds.
        Useful for external monitoring tools; the UI wires pause/resume/cancel
        via the runner's own methods instead.
    """

    log_line = Signal(str)
    awaiting_login = Signal()
    progress = Signal(int)
    finished_ok = Signal()
    finished_error = Signal(str)
    process_started = Signal(int)

    def __init__(
        self,
        python_exe: str,
        pipeline_dir: str,
        env_overrides: dict[str, str],
        total_rows_hint: Optional[int] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.python_exe = python_exe
        self.pipeline_dir = pipeline_dir
        self.env_overrides = env_overrides
        self.total_rows_hint = total_rows_hint

        self._proc: Optional[subprocess.Popen] = None
        self._claims_seen: int = 0
        self._cancel_requested: bool = False
        self._login_emitted: bool = False

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Main QThread body.  Runs entirely on the worker thread."""
        env = os.environ.copy()
        env.update(self.env_overrides)

        # Ensure Python stdout is line-buffered even when piped.
        env["PYTHONUNBUFFERED"] = "1"

        try:
            self._proc = subprocess.Popen(
                [self.python_exe, "verify_colleges.py"],
                cwd=self.pipeline_dir,
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
            self.finished_error.emit(
                f"Could not find Python interpreter:\n  {self.python_exe}\n\n"
                "Check the 'Python Interpreter' path in Settings."
            )
            return
        except Exception as exc:
            self.finished_error.emit(f"Failed to launch pipeline:\n{exc}")
            return

        self.process_started.emit(self._proc.pid)

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
                self.log_line.emit(_strip_ansi(line))

                # Detect human-in-the-loop pause (emitted only once).
                if not self._login_emitted and LOGIN_PROMPT_MARKER in line:
                    self._login_emitted = True
                    self.awaiting_login.emit()

                # Track per-claim progress via Acknowledgement: lines.
                if ACK_LINE_RE.search(line):
                    self._claims_seen += 1
                    self.progress.emit(self._claims_seen)
            else:
                # No newline yet — check the in-progress buffer.
                # input()'s prompt will never produce a newline, so this is
                # the only way to catch LOGIN_PROMPT_MARKER in that case.
                if not self._login_emitted and LOGIN_PROMPT_MARKER in buffer:
                    self._login_emitted = True
                    self.log_line.emit(_strip_ansi(buffer))
                    self.awaiting_login.emit()
                    buffer = ""   # consumed — don't re-emit when \n arrives

        # Flush any partial line left in the buffer at EOF.
        if buffer:
            self.log_line.emit(_strip_ansi(buffer))

        returncode = self._proc.wait()

        if self._cancel_requested:
            self.finished_error.emit("Run cancelled by user.")
        elif returncode == 0:
            self.finished_ok.emit()
        else:
            self.finished_error.emit(
                f"Pipeline exited with code {returncode}.\n"
                "Check the log pane above for details."
            )

    # ------------------------------------------------------------------
    # Control methods — safe to call from the GUI thread
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
        Request cancellation.  Sets the flag first so the finished_error
        signal carries the 'cancelled' message rather than the raw exit code.
        """
        self._cancel_requested = True
        if self._proc:
            try:
                psutil.Process(self._proc.pid).terminate()
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

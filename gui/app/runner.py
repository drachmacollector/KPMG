"""
app/runner.py

PipelineRunner — manages the verify_colleges.py subprocess.

The pipeline prints machine-readable event lines
    @@MAHABOCW {"event": "...", ...}
(see logger_config.emit_event).  The runner turns them into push events for
the React frontend and hides them from the log pane.  Ordinary log lines are
batched (one evaluate_js call per ~100 ms) so a chatty run cannot flood the
WebView bridge.

Push events (via Api):
    pipeline-log            {"lines": [str, ...]}
    pipeline-event          the raw pipeline event dict (claim_start, claim_done, ...)
    pipeline-awaiting-login {}
    pipeline-progress       {"count": int, "total": int | None}
    pipeline-done           {"claims_seen", "output_file", "summary", "stopped"}
    pipeline-error          {"message": str}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from typing import Optional

import psutil

from app.settings import DATA_DIR, STOP_FILE, Settings

EVENT_PREFIX = "@@MAHABOCW "

# Fallbacks for an older pipeline that does not emit events.
LOGIN_PROMPT_MARKER = "Press ENTER here"
ACK_LINE_RE = re.compile(r"Acknowledgement:\s*(\S+)")

# Strip ANSI colour/style escape sequences.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

LOG_FLUSH_SECS = 0.1
FORCE_STOP_WAIT_SECS = 5

# Windows: don't flash a console window for the child process.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class PipelineRunner:
    """Manages a single run of verify_colleges.py as a subprocess."""

    def __init__(self, api_ref, settings: dict) -> None:
        self.api = api_ref
        self._typed: Settings = Settings.from_dict(settings)
        self._total_rows: Optional[int] = settings.get("_total_rows_hint")

        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._claims_seen: int = 0
        self._cancel_requested: bool = False
        self._stop_requested: bool = False
        self._login_emitted: bool = False
        self._run_started: bool = False
        self._uses_events: bool = False
        self._summary: Optional[dict] = None
        self._stopped_cleanly: bool = False
        self._preflight_problems: list = []
        self._paused: bool = False

        self._pending: list[str] = []
        self._lock = threading.Lock()
        self._reader_done = threading.Event()

    # ------------------------------------------------------------------
    # Thread management
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        threading.Thread(target=self._flush_loop, daemon=True).start()

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _log(self, line: str) -> None:
        with self._lock:
            self._pending.append(line)

    def _flush(self) -> None:
        with self._lock:
            lines, self._pending = self._pending, []
        if lines:
            self.api.push_log({"lines": lines})

    def _flush_loop(self) -> None:
        while not self._reader_done.is_set():
            time.sleep(LOG_FLUSH_SECS)
            self._flush()
        self._flush()

    def _run(self) -> None:
        try:
            self._run_inner()
        finally:
            self._reader_done.set()

    def _run_inner(self) -> None:
        env = os.environ.copy()
        env.update(self._typed.build_env_overrides())
        env["PYTHONUNBUFFERED"] = "1"

        python_exe = self._typed.effective_python_exe()
        pipeline_dir = self._typed.effective_pipeline_dir()
        script = os.path.join(pipeline_dir, "verify_colleges.py")

        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            os.remove(STOP_FILE)
        except OSError:
            pass

        if not os.path.isfile(script):
            self._reader_done.set()
            self.api.push_error({"message": f"The pipeline was not found at:\n  {script}\n\nReinstall MAHABOCW or fix the pipeline folder under Settings → Advanced."})
            return

        try:
            self._proc = subprocess.Popen(
                [python_exe, script],
                cwd=DATA_DIR,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=_CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            self.api.push_error({"message": f"Could not find the Python runtime:\n  {python_exe}\n\nReinstall MAHABOCW or fix the interpreter under Settings → Advanced."})
            return
        except Exception as exc:
            self.api.push_error({"message": f"Failed to launch pipeline:\n{exc}"})
            return

        # Character-level reader: input()'s prompt has no trailing newline, so
        # a line iterator would never see it (needed for the legacy fallback).
        buffer = ""
        while True:
            ch = self._proc.stdout.read(1)
            if ch == "":
                break
            if ch in ("\n", "\r"):
                line, buffer = buffer, ""
                if line.strip():
                    self._handle_line(_strip_ansi(line))
                continue
            buffer += ch
            if not self._login_emitted and LOGIN_PROMPT_MARKER in buffer:
                self._log(_strip_ansi(buffer))
                self._emit_login()
                buffer = ""

        if buffer.strip():
            self._handle_line(_strip_ansi(buffer))

        returncode = self._proc.wait()
        self._reader_done.set()
        self._flush()
        try:
            os.remove(STOP_FILE)
        except OSError:
            pass

        if self._cancel_requested:
            self.api.push_error({"message": "Run force-stopped. Progress saved before the stop is kept; the next run resumes from there."})
        elif self._preflight_problems:
            self.api.push_error({"message": "The run could not start:\n\n• " + "\n• ".join(self._preflight_problems)})
        elif returncode == 0:
            self.api.push_done({
                "claims_seen": self._claims_seen,
                "output_file": self._typed.output_file,
                "summary": self._summary,
                "stopped": self._stopped_cleanly,
            })
        else:
            self.api.push_error({"message": f"The pipeline stopped with an error (exit code {returncode}).\nSee the log above for details."})

    # ------------------------------------------------------------------
    # Line / event handling
    # ------------------------------------------------------------------

    def _emit_login(self) -> None:
        if not self._login_emitted:
            self._login_emitted = True
            self._flush()
            self.api.push_awaiting_login()

    def _handle_line(self, line: str) -> None:
        # input()'s prompt has no trailing newline, so the next event can be
        # glued onto it: "Press ENTER ...@@MAHABOCW {...}".  Split it off.
        idx = line.find(EVENT_PREFIX)
        if idx > 0:
            head, line = line[:idx], line[idx:]
            if head.strip():
                self._handle_line(head)
        if line.startswith(EVENT_PREFIX):
            try:
                event = json.loads(line[len(EVENT_PREFIX):])
            except json.JSONDecodeError:
                self._log(line)
                return
            self._uses_events = True
            self._handle_event(event)
            return

        self._log(line)

        if not self._login_emitted and LOGIN_PROMPT_MARKER in line:
            self._emit_login()
        if not self._uses_events and ACK_LINE_RE.search(line):
            self._claims_seen += 1
            self.api.push_progress({"count": self._claims_seen, "total": self._total_rows})

    def _handle_event(self, event: dict) -> None:
        name = event.get("event")
        if name == "awaiting_login":
            self._emit_login()
            return
        if name == "run_start":
            self._run_started = True
            if event.get("total") is not None:
                self._total_rows = event["total"]
        elif name in ("claim_done", "claim_skipped"):
            self._claims_seen = int(event.get("n") or self._claims_seen + 1)
            self.api.push_progress({"count": self._claims_seen, "total": self._total_rows})
        elif name == "run_end":
            self._summary = event.get("summary")
            self._stopped_cleanly = bool(event.get("stopped"))
        elif name == "preflight_failed":
            self._preflight_problems = list(event.get("problems") or [])
        self._flush()
        self.api.push_event(event)

    # ------------------------------------------------------------------
    # Control methods — safe to call from any thread
    # ------------------------------------------------------------------

    def confirm_login(self) -> None:
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.write("\n")
                self._proc.stdin.flush()
            except OSError:
                pass

    def pause(self) -> None:
        if self._proc:
            try:
                psutil.Process(self._proc.pid).suspend()
                self._paused = True
            except psutil.Error:
                pass

    def resume(self) -> None:
        if self._proc:
            try:
                psutil.Process(self._proc.pid).resume()
                self._paused = False
            except psutil.Error:
                pass

    def stop(self) -> None:
        """
        Graceful stop: ask the pipeline to finish the current claim, save, and
        exit.  Before the claim loop has started (e.g. while waiting for the
        portal login) there is nothing to finish, so this force-stops.
        """
        if not self._run_started:
            self.force_stop()
            return
        self._stop_requested = True
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(STOP_FILE, "w", encoding="utf-8") as fh:
                fh.write("stop")
        except OSError:
            self.force_stop()
            return
        if self._paused:
            self.resume()

    def force_stop(self) -> None:
        """Terminate the pipeline and every child (Playwright's chrome.exe)."""
        self._cancel_requested = True
        if not self._proc:
            return
        try:
            parent = psutil.Process(self._proc.pid)
            procs = parent.children(recursive=True) + [parent]
            for p in procs:
                try:
                    p.resume()  # a suspended process can't handle termination cleanly
                except psutil.Error:
                    pass
            for p in procs:
                try:
                    p.terminate()
                except psutil.Error:
                    pass
            _, alive = psutil.wait_procs(procs, timeout=FORCE_STOP_WAIT_SECS)
            for p in alive:
                try:
                    p.kill()
                except psutil.Error:
                    pass
        except psutil.Error:
            pass

    # Back-compat alias.
    cancel = force_stop

    @property
    def claims_seen(self) -> int:
        return self._claims_seen

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

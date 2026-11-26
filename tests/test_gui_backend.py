import json
import os
import sys
import textwrap
import threading
import time

import pytest

pytest.importorskip("psutil")

from app import settings as settings_mod  # noqa: E402
import app.runner as runner_mod  # noqa: E402
from app.runner import PipelineRunner  # noqa: E402


DUMMY_PIPELINE = textwrap.dedent("""
    import json, os, sys, time
    def ev(name, **kw):
        print("@@MAHABOCW " + json.dumps({"event": name, **kw}), flush=True)
    print("Human Setup Required", flush=True)
    ev("awaiting_login")
    input("Press ENTER here in the terminal when you are ready to start the loop...")
    total = 4
    ev("run_start", total=total)
    ev("claim_skipped", n=1, total=total, ack="A1", reason="already processed")
    stopped = False
    for n in range(2, total + 1):
        if os.path.exists(os.environ["MAHABOCW_STOP_FILE"]):
            stopped = True
            break
        ev("claim_start", n=n, total=total, ack=f"A{n}")
        print(f"Acknowledgement: A{n}", flush=True)
        time.sleep(float(os.environ.get("DUMMY_DELAY", "0.05")))
        ev("claim_done", n=n, total=total, ack=f"A{n}", status="VERIFIED", accuracy=90,
           manual_review=False, college="X", via_cache=False)
    ev("run_end", stopped=stopped, total=total, summary={"VERIFIED": 3})
""")


class FakeApi:
    def __init__(self):
        self.events = []
        self.done = threading.Event()

    def _rec(self, kind, payload=None):
        self.events.append((kind, payload))

    def push_log(self, p): self._rec("log", p)
    def push_event(self, p): self._rec("event", p)
    def push_progress(self, p): self._rec("progress", p)
    def push_awaiting_login(self): self._rec("login")
    def push_done(self, p): self._rec("done", p); self.done.set()
    def push_error(self, p): self._rec("error", p); self.done.set()


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    (tmp_path / "verify_colleges.py").write_text(DUMMY_PIPELINE, encoding="utf-8")
    data = tmp_path / "data"
    stop = str(data / ".stop")
    for mod in (settings_mod, runner_mod):
        monkeypatch.setattr(mod, "DATA_DIR", str(data))
        monkeypatch.setattr(mod, "STOP_FILE", stop)
    return {"pipeline_dir": str(tmp_path), "python_exe": sys.executable,
            "input_file": "in.xlsx", "sheet_name": "S", "output_file": "out.xlsx"}


def _wait_for(api, kind, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(k == kind for k, _ in api.events):
            return True
        time.sleep(0.05)
    return False


def test_runner_full_run_counts_skipped_rows(pipeline):
    api = FakeApi()
    r = PipelineRunner(api, pipeline)
    r.start()
    assert _wait_for(api, "login")
    r.confirm_login()
    assert api.done.wait(20)
    kinds = [k for k, _ in api.events]
    assert "error" not in kinds
    progress = [p for k, p in api.events if k == "progress"]
    assert progress[-1] == {"count": 4, "total": 4}
    done = [p for k, p in api.events if k == "done"][0]
    assert done["summary"] == {"VERIFIED": 3} and done["stopped"] is False
    logs = [line for k, p in api.events if k == "log" for line in p["lines"]]
    assert not any(line.startswith("@@MAHABOCW") for line in logs)
    assert kinds.count("login") == 1


def test_runner_graceful_stop(pipeline, monkeypatch):
    monkeypatch.setenv("DUMMY_DELAY", "1.0")
    api = FakeApi()
    r = PipelineRunner(api, pipeline)
    r.start()
    assert _wait_for(api, "login")
    r.confirm_login()
    deadline = time.time() + 10
    while not r._run_started and time.time() < deadline:
        time.sleep(0.05)
    r.stop()
    assert api.done.wait(20)
    done = [p for k, p in api.events if k == "done"][0]
    assert done["stopped"] is True


def test_runner_stop_before_login_force_stops(pipeline):
    api = FakeApi()
    r = PipelineRunner(api, pipeline)
    r.start()
    assert _wait_for(api, "login")
    r.stop()
    assert api.done.wait(20)
    assert [k for k, _ in api.events if k in ("done", "error")] == ["error"]


def test_settings_roundtrip_encrypts_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(settings_mod, "CONFIG_PATH", str(tmp_path / "settings.json"))
    settings_mod.save_settings({"gemini_api_key": "secret-123", "delete_downloads": False, "unknown": 1})
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    if os.name == "nt":
        assert raw["gemini_api_key"].startswith("dpapi:")
    loaded = settings_mod.load_settings()
    assert loaded["gemini_api_key"] == "secret-123"
    assert loaded["delete_downloads"] is False


def test_env_overrides_include_stop_file_and_range():
    s = settings_mod.Settings(process_mode="range", start_row="2", end_row="9")
    env = s.build_env_overrides()
    assert env["EXCEL_PROCESS_ALL"] == "false"
    assert env["EXCEL_START_ROW"] == "2" and env["EXCEL_END_ROW"] == "9"
    assert env["MAHABOCW_STOP_FILE"] == settings_mod.STOP_FILE

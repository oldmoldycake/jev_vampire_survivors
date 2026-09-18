import json
import time
from pathlib import Path

from jev_vs.runlog import RunLog


def test_runlog_writes_jsonl_and_summary(tmp_path: Path):
    log = RunLog(tmp_path)
    assert log.active is False
    run_dir = log.start_run({"character": "ANTONIO"})
    assert log.active is True and run_dir.is_dir() and run_dir.parent == tmp_path
    log.tick({"id": 1, "choice": "north"})
    log.tick({"id": 2, "choice": "stay"})
    log.event({"event": "level_up", "index": 0})
    summary = log.end_run({"seconds": 42})
    assert log.active is False
    ticks = [json.loads(l) for l in (run_dir / "ticks.jsonl").read_text().splitlines()]
    assert [t["id"] for t in ticks] == [1, 2]
    events = [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines()]
    assert events[0]["event"] == "level_up"
    written = json.loads((run_dir / "summary.json").read_text())
    assert written["seconds"] == 42 and written["character"] == "ANTONIO" and written["ticks"] == 2
    assert summary == written


def test_tick_before_start_is_buffered_into_next_run(tmp_path: Path):
    log = RunLog(tmp_path)
    log.tick({"id": 0})
    run_dir = log.start_run({})
    log.end_run({})
    assert (run_dir / "ticks.jsonl").read_text().count("\n") == 1


def test_pending_buffer_is_bounded(tmp_path: Path):
    log = RunLog(tmp_path)
    for i in range(100):
        log.tick({"id": i})
    run_dir = log.start_run({})
    log.end_run({})
    lines = (run_dir / "ticks.jsonl").read_text().splitlines()
    assert len(lines) <= 64


def test_end_run_on_inactive_log_clears_pending_buffer(tmp_path: Path):
    log = RunLog(tmp_path)
    log.tick({"id": 0})
    log.tick({"id": 1})
    written = log.end_run({})
    assert written == {}
    run_dir = log.start_run({})
    log.end_run({})
    assert (run_dir / "ticks.jsonl").read_text() == ""


def test_buffered_record_keeps_its_arrival_time(tmp_path: Path):
    log = RunLog(tmp_path)
    log.tick({"id": 0})
    arrival = time.time()
    time.sleep(0.05)
    run_dir = log.start_run({})
    start_time = time.time()
    log.end_run({})
    ticks = [json.loads(l) for l in (run_dir / "ticks.jsonl").read_text().splitlines()]
    assert len(ticks) == 1
    assert ticks[0]["t"] < start_time
    assert ticks[0]["t"] <= arrival + 0.05

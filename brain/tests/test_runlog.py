import json
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

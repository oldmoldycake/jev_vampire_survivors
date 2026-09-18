"""JSONL run logs: runs/<YYYYMMDD-HHMMSS>/{ticks.jsonl,events.jsonl,summary.json}."""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

_PENDING_MAXLEN = 64


class RunLog:
    def __init__(self, root: Path):
        self._root = Path(root)
        self._run_dir: Path | None = None
        self._meta: dict = {}
        self._ticks = None
        self._events = None
        self._tick_count = 0
        self._event_count = 0
        self._pending: deque[tuple[str, dict]] = deque(maxlen=_PENDING_MAXLEN)

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir

    @property
    def active(self) -> bool:
        return self._run_dir is not None

    def start_run(self, meta: dict) -> Path:
        if self.active:
            self.end_run({"aborted": True})
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run_dir = self._root / stamp
        n = 1
        while run_dir.exists():
            n += 1
            run_dir = self._root / f"{stamp}-{n}"
        run_dir.mkdir(parents=True)
        self._run_dir = run_dir
        self._meta = {"started_at": time.time(), **meta}
        self._ticks = (run_dir / "ticks.jsonl").open("a", encoding="utf-8")
        self._events = (run_dir / "events.jsonl").open("a", encoding="utf-8")
        self._tick_count = self._event_count = 0
        for kind, rec in self._pending:
            (self.tick if kind == "tick" else self.event)(rec)
        self._pending.clear()
        return run_dir

    def _write(self, fh, record: dict) -> None:
        fh.write(json.dumps({"t": time.time(), **record}, separators=(",", ":"), ensure_ascii=False) + "\n")
        fh.flush()

    def tick(self, record: dict) -> None:
        if not self.active:
            # Stamp arrival time now so a later flush (in start_run) doesn't
            # relabel this record with the flush time instead.
            self._pending.append(("tick", {"t": time.time(), **record}))
            return
        self._tick_count += 1
        self._write(self._ticks, record)

    def event(self, record: dict) -> None:
        if not self.active:
            self._pending.append(("event", {"t": time.time(), **record}))
            return
        self._event_count += 1
        self._write(self._events, record)

    def update_meta(self, **fields) -> None:
        self._meta.update(fields)

    def end_run(self, summary: dict) -> dict:
        if not self.active:
            self._pending.clear()
            return {}
        written = {**self._meta, **summary, "ended_at": time.time(),
                   "ticks": self._tick_count, "events": self._event_count}
        (self._run_dir / "summary.json").write_text(json.dumps(written, indent=2))
        self._ticks.close()
        self._events.close()
        self._run_dir = None
        self._ticks = self._events = None
        return written

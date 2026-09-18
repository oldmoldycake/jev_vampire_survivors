import asyncio
import json
from pathlib import Path

import pytest

from jev_vs.config import Config
from jev_vs.decide import Decider
from jev_vs.hub import Hub
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from jev_vs.runlog import RunLog
from jev_vs.server import PluginServer
from jev_vs.stats import Stats
from tests.conftest import FakeJev, make_state


class SlowJev(FakeJev):
    """First call blocks until released, so the second tick overlaps it."""

    def __init__(self):
        super().__init__(script={"direction": ("east", {"east": 1.0}, 0.9)})
        self.gate = asyncio.Event()
        self.n = 0

    async def ask(self, state, questions):
        self.n += 1
        if self.n == 1:
            await self.gate.wait()
        return await super().ask(state, questions)


async def _start(tmp_path: Path, jev):
    hub = Hub()
    stats = Stats()
    srv = PluginServer(Config(plugin_port=0, log_dir=str(tmp_path)), Decider(jev, TH), RunLog(tmp_path), hub, stats)
    port = await srv.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    return srv, hub, stats, reader, writer


async def _send(writer, msg):
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()


async def _recv(reader):
    return json.loads(await asyncio.wait_for(reader.readline(), 2))


async def test_hello_and_tick_round_trip(tmp_path):
    jev = FakeJev(script={"direction": ("west", {"west": 0.6, "stay": 0.4}, 0.2)})
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    q = hub.subscribe()
    await _send(writer, {"type": "hello", "game_version": "1.16.107", "plugin_version": "0.1.0"})
    await _send(writer, {"id": 1, "type": "tick", "t": 0.25, "state": make_state()})
    reply = await _recv(reader)
    assert reply["id"] == 1 and reply["type"] == "move" and reply["choice"] == "west"
    assert (reply["dx"], reply["dy"]) == (-1.0, 0.0) and reply["source"] == "jev"
    msgs = [await q.get() for _ in range(3)]
    kinds = [m["type"] for m in msgs]
    assert "stats" in kinds and "decision" in kinds
    dec = next(m for m in msgs if m["type"] == "decision")
    assert dec["kind"] == "direction" and "digest" in dec and "entities" in dec
    assert stats.snapshot()["plugin_connected"] is True and stats.snapshot()["calls"] == 1
    writer.close()
    await srv.stop()


async def test_overlapping_tick_gets_reused_reply(tmp_path):
    jev = SlowJev()
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    await _send(writer, {"id": 1, "type": "tick", "t": 0.0, "state": make_state()})
    await asyncio.sleep(0.05)
    await _send(writer, {"id": 2, "type": "tick", "t": 0.25, "state": make_state()})
    second = await _recv(reader)
    assert second["id"] == 2 and second["source"] == "reused" and second["choice"] == "stay"
    jev.gate.set()
    first = await _recv(reader)
    assert first["id"] == 1 and first["choice"] == "east" and first["source"] == "jev"
    assert stats.snapshot()["reused"] == 1
    writer.close()
    await srv.stop()


async def test_stop_cancels_in_flight_tasks(tmp_path):
    jev = SlowJev()   # first ask blocks until the gate is set; we never set it
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    await _send(writer, {"id": 1, "type": "tick", "t": 0.0, "state": make_state()})
    await asyncio.sleep(0.05)
    assert len(srv._tasks) == 1
    writer.close()
    await asyncio.wait_for(srv.stop(), 1.0)
    assert srv._tasks == set()


async def test_events_drive_run_log_and_picks(tmp_path):
    jev = FakeJev(script={"character": ("IMELDA", {"IMELDA": 0.9, "ANTONIO": 0.1}, 0.8),
                         "level_up": ("SPINACH", {"SPINACH": 1.0}, 1.0)})
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    chars = [{"id": "ANTONIO", "name": "Antonio", "description": "d"}, {"id": "IMELDA", "name": "Imelda", "description": "d"}]
    await _send(writer, {"id": 10, "type": "event", "event": "character_select", "options": chars})
    r = await _recv(reader)
    assert r == {"id": 10, "type": "pick", "index": 1, "choice": "IMELDA",
                 "probabilities": {"IMELDA": 0.9, "ANTONIO": 0.1}, "confidence": 0.8, "source": "jev"}
    assert srv.runlog.active is True
    await _send(writer, {"id": 11, "type": "event", "event": "stage_select",
                         "options": [{"id": "FOREST", "name": "Mad Forest", "description": "d"}]})
    assert (await _recv(reader))["choice"] == "FOREST"
    await _send(writer, {"id": 12, "type": "event", "event": "level_up",
                         "options": [{"index": 0, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 1}],
                         "build": {"weapons": [], "passives": []}})
    assert (await _recv(reader))["index"] == 0
    await _send(writer, {"id": 13, "type": "event", "event": "game_over",
                         "summary": {"character": "IMELDA", "stage": "FOREST", "seconds": 90, "level": 4, "kills": 12, "stage_complete": False}})
    assert (await _recv(reader)) == {"id": 13, "type": "noop"}
    assert srv.runlog.active is False
    assert srv.run_history[-1]["character"] == "IMELDA" and srv.run_history[-1]["seconds"] == 90
    assert srv.run_history[-1]["jev_calls"] == 3
    run_dirs = [p for p in Path(tmp_path).iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "summary.json").read_text())
    assert summary["character"] == "IMELDA" and summary["stage"] == "FOREST" and summary["seconds"] == 90
    assert summary["jev_calls"] == 3 and summary["fallback_calls"] == 0
    events = (run_dirs[0] / "events.jsonl").read_text().splitlines()
    assert len(events) == 4
    writer.close()
    await srv.stop()


async def test_game_over_with_no_active_run_does_not_add_history_row(tmp_path):
    srv, hub, stats, reader, writer = await _start(tmp_path, FakeJev())
    before = len(srv.run_history)
    await _send(writer, {"id": 1, "type": "event", "event": "game_over",
                         "summary": {"character": "NOBODY", "stage": "NONE", "seconds": 0, "level": 1}})
    assert (await _recv(reader)) == {"id": 1, "type": "noop"}
    assert len(srv.run_history) == before
    writer.close()
    await srv.stop()


async def test_pick_reply_echoes_options_own_index(tmp_path):
    jev = FakeJev(script={"character": ("B", {"A": 0.0, "B": 1.0}, 1.0)})
    srv, hub, stats, reader, writer = await _start(tmp_path, jev)
    opts = [{"id": "A", "name": "A", "index": 7, "description": "d"},
            {"id": "B", "name": "B", "index": 9, "description": "d"}]
    await _send(writer, {"id": 1, "type": "event", "event": "character_select", "options": opts})
    reply = await _recv(reader)
    assert reply["index"] == 9 and reply["choice"] == "B"
    writer.close()
    await srv.stop()


async def test_bad_line_is_skipped_and_connection_survives(tmp_path):
    srv, hub, stats, reader, writer = await _start(tmp_path, FakeJev())
    writer.write(b"garbage\n")
    await _send(writer, {"id": 5, "type": "tick", "t": 0.0, "state": make_state()})
    assert (await _recv(reader))["id"] == 5
    writer.close()
    await srv.stop()


async def test_send_control_reaches_plugin_and_reports_absence(tmp_path):
    srv, hub, stats, reader, writer = await _start(tmp_path, FakeJev())
    await _send(writer, {"type": "hello"})
    await asyncio.sleep(0.05)
    assert await srv.send_control(False) is True
    assert (await _recv(reader)) == {"type": "control", "automation": False}
    writer.close()
    await asyncio.sleep(0.05)
    assert await srv.send_control(True) is False
    assert stats.snapshot()["plugin_connected"] is False
    await srv.stop()

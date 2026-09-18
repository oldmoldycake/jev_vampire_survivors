import asyncio
import json

import aiohttp
import pytest
from aiohttp import WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from jev_vs.config import Config
from jev_vs.dashboard import make_app
from jev_vs.decide import Decider, Decision
from jev_vs.hub import Hub
from jev_vs.pins import PinStore
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from jev_vs.runlog import RunLog
from jev_vs.server import PluginServer
from jev_vs.stats import Stats
from tests.conftest import FakeJev


@pytest.fixture
async def plugin_server(tmp_path):
    srv = PluginServer(
        Config(plugin_port=0, log_dir=str(tmp_path)),
        Decider(FakeJev(), TH),
        RunLog(tmp_path),
        Hub(maxsize=4),
        Stats(),
        PinStore(tmp_path / "pins.json"),
    )
    await srv.start()
    yield srv
    await srv.stop()


@pytest.fixture
async def client(plugin_server):
    app = make_app(plugin_server)
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_index_serves_page(client):
    resp = await client.get("/")
    assert resp.status == 200
    body = await resp.text()
    low = body.lower()
    assert "<title>" in body and "WebSocket" in body
    # the four panels the dashboard is made of, so a broken page fails here rather than silently
    for panel in ("arena", "decisions", "log", "runs this session"):
        assert panel in low, panel


async def test_ws_snapshot_then_decision(client, plugin_server):
    ws = await client.ws_connect("/ws")
    snap = json.loads((await ws.receive()).data)
    assert snap["type"] == "snapshot" and "stats" in snap and "decisions" in snap
    d = Decision(
        kind="direction",
        choice="north",
        index=0,
        probabilities={"north": 1.0},
        confidence=0.4,
        latency_ms=90.0,
        source="jev",
        input_tokens=50,
    )
    plugin_server._record_decision(d, digest={}, entities={})
    got = json.loads((await ws.receive()).data)
    assert got["type"] == "decision" and got["choice"] == "north"
    await ws.close()


async def test_ws_control_forwards_to_plugin(client, plugin_server):
    reader, writer = await asyncio.open_connection("127.0.0.1", plugin_server.port)
    await asyncio.sleep(0.05)
    ws = await client.ws_connect("/ws")
    await ws.receive()  # snapshot
    await ws.send_str(json.dumps({"type": "control", "automation": False}))
    line = json.loads(await asyncio.wait_for(reader.readline(), 2))
    assert line == {"type": "control", "automation": False}
    writer.close()
    await ws.close()


async def test_slow_ws_client_is_dropped_without_blocking(client, plugin_server):
    ws = await client.ws_connect("/ws")
    await ws.receive()
    for i in range(20):  # hub maxsize is 4; the client never reads
        plugin_server.hub.publish({"type": "stats", "n": i})
    await asyncio.sleep(0.1)
    assert plugin_server.hub.client_count == 0
    msg = await ws.receive()
    assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.TEXT)


async def test_ws_ignores_non_object_json(client, plugin_server):
    reader, writer = await asyncio.open_connection("127.0.0.1", plugin_server.port)
    await asyncio.sleep(0.05)
    ws = await client.ws_connect("/ws")
    await ws.receive()  # snapshot
    await ws.send_str("42")
    await ws.send_str("[1, 2]")
    await ws.send_str(json.dumps({"type": "control", "automation": False}))
    line = json.loads(await asyncio.wait_for(reader.readline(), 2))
    assert line == {"type": "control", "automation": False}
    writer.close()
    await ws.close()


async def test_ws_rejects_foreign_origin_but_allows_own_host(client, plugin_server):
    with pytest.raises(aiohttp.WSServerHandshakeError) as exc_info:
        await client.ws_connect("/ws", headers={"Origin": "http://evil.example"})
    assert exc_info.value.status == 403
    ws = await client.ws_connect("/ws", headers={"Origin": f"http://{client.host}:{client.port}"})
    snap = json.loads((await ws.receive()).data)
    assert snap["type"] == "snapshot"
    await ws.close()


async def test_snapshot_includes_run_history(client, plugin_server):
    plugin_server.run_history.append(
        {"character": "IMELDA", "stage": "FOREST", "seconds": 90, "level": 4, "jev_calls": 3, "fallback_calls": 0}
    )
    ws = await client.ws_connect("/ws")
    snap = json.loads((await ws.receive()).data)
    assert snap["runs"][0]["character"] == "IMELDA"
    await ws.close()


async def _wait_for(predicate, timeout=2.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def test_index_offers_a_character_and_a_stage_select(client):
    body = await (await client.get("/")).text()
    assert 'id="pin-character"' in body and 'id="pin-stage"' in body
    assert "JEV DECIDES" in body


async def test_snapshot_carries_pins_and_rosters(client, plugin_server):
    plugin_server.pins.set_pin("character", "ANTONIO")
    plugin_server.pins.remember_options("stage", [{"id": "FOREST", "name": "Mad Forest"}])
    ws = await client.ws_connect("/ws")
    snap = json.loads((await ws.receive()).data)
    assert snap["pins"] == {"character": "ANTONIO", "stage": None}
    assert snap["rosters"]["stage"] == [{"id": "FOREST", "name": "Mad Forest"}]
    await ws.close()


async def test_ws_pin_message_reaches_the_store_and_can_clear_it(client, plugin_server):
    ws = await client.ws_connect("/ws")
    await ws.receive()  # snapshot
    await ws.send_str(json.dumps({"type": "pin", "kind": "character", "id": "IMELDA"}))
    assert await _wait_for(lambda: plugin_server.pins.pin_for("character") == "IMELDA")
    await ws.send_str(json.dumps({"type": "pin", "kind": "character", "id": None}))
    assert await _wait_for(lambda: plugin_server.pins.pin_for("character") is None)
    await ws.close()


async def test_ws_ignores_a_malformed_pin_message(client, plugin_server):
    ws = await client.ws_connect("/ws")
    await ws.receive()  # snapshot
    await ws.send_str(json.dumps({"type": "pin", "kind": 7, "id": "ANTONIO"}))
    await ws.send_str(json.dumps({"type": "pin", "kind": "character", "id": 12}))
    await ws.send_str(json.dumps({"type": "pin", "kind": "stage", "id": "FOREST"}))
    # the good one lands, which proves the bad two were dropped rather than fatal
    assert await _wait_for(lambda: plugin_server.pins.pin_for("stage") == "FOREST")
    assert plugin_server.pins.pin_for("character") is None
    await ws.close()

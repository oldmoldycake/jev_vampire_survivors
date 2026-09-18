import asyncio
import json

import pytest
from aiohttp import WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from jev_vs.config import Config
from jev_vs.dashboard import make_app
from jev_vs.decide import Decider, Decision
from jev_vs.hub import Hub
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from jev_vs.runlog import RunLog
from jev_vs.server import PluginServer
from jev_vs.stats import Stats
from tests.conftest import FakeJev


@pytest.fixture
async def plugin_server(tmp_path):
    srv = PluginServer(Config(plugin_port=0, log_dir=str(tmp_path)), Decider(FakeJev(), TH), RunLog(tmp_path), Hub(maxsize=4), Stats())
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
    assert "<title>" in body and "judgments" in body.lower() and "WebSocket" in body


async def test_ws_snapshot_then_decision(client, plugin_server):
    ws = await client.ws_connect("/ws")
    snap = json.loads((await ws.receive()).data)
    assert snap["type"] == "snapshot" and "stats" in snap and "decisions" in snap
    d = Decision(kind="direction", choice="north", index=0, probabilities={"north": 1.0}, confidence=0.4,
                 latency_ms=90.0, source="jev", input_tokens=50)
    plugin_server._record_decision(d, digest={}, entities={})
    got = json.loads((await ws.receive()).data)
    assert got["type"] == "decision" and got["choice"] == "north"
    await ws.close()


async def test_ws_control_forwards_to_plugin(client, plugin_server):
    reader, writer = await asyncio.open_connection("127.0.0.1", plugin_server.port)
    await asyncio.sleep(0.05)
    ws = await client.ws_connect("/ws")
    await ws.receive()   # snapshot
    await ws.send_str(json.dumps({"type": "control", "automation": False}))
    line = json.loads(await asyncio.wait_for(reader.readline(), 2))
    assert line == {"type": "control", "automation": False}
    writer.close()
    await ws.close()


async def test_slow_ws_client_is_dropped_without_blocking(client, plugin_server):
    ws = await client.ws_connect("/ws")
    await ws.receive()
    for i in range(20):   # hub maxsize is 4; the client never reads
        plugin_server.hub.publish({"type": "stats", "n": i})
    await asyncio.sleep(0.1)
    assert plugin_server.hub.client_count == 0
    msg = await ws.receive()
    assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.TEXT)


async def test_ws_ignores_non_object_json(client, plugin_server):
    reader, writer = await asyncio.open_connection("127.0.0.1", plugin_server.port)
    await asyncio.sleep(0.05)
    ws = await client.ws_connect("/ws")
    await ws.receive()   # snapshot
    await ws.send_str("42")
    await ws.send_str("[1, 2]")
    await ws.send_str(json.dumps({"type": "control", "automation": False}))
    line = json.loads(await asyncio.wait_for(reader.readline(), 2))
    assert line == {"type": "control", "automation": False}
    writer.close()
    await ws.close()


async def test_snapshot_includes_run_history(client, plugin_server):
    plugin_server.run_history.append({"character": "IMELDA", "stage": "FOREST", "seconds": 90, "level": 4, "jev_calls": 3, "fallback_calls": 0})
    ws = await client.ws_connect("/ws")
    snap = json.loads((await ws.receive()).data)
    assert snap["runs"][0]["character"] == "IMELDA"
    await ws.close()

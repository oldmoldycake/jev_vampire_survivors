"""Live dashboard: one static page plus a WebSocket fed by the Hub."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import WSMsgType, web

from .server import PluginServer

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def _allowed_origins(request: web.Request) -> set[str]:
    """Origins a browser WebSocket upgrade may come from: this dashboard's own host, by name or address."""
    host = request.host  # e.g. "127.0.0.1:48232"; already "host:port" per the Host header
    allowed = {f"http://{host}"}
    port = host.rsplit(":", 1)[-1] if ":" in host else None
    if port:
        allowed.add(f"http://127.0.0.1:{port}")
        allowed.add(f"http://localhost:{port}")
    return allowed


def make_app(server: PluginServer) -> web.Application:
    app = web.Application()

    async def index(_request: web.Request) -> web.Response:
        return web.Response(text=(STATIC / "index.html").read_text(encoding="utf-8"), content_type="text/html")

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        origin = request.headers.get("Origin")
        if origin and origin not in _allowed_origins(request):
            log.warning("rejected websocket upgrade from origin %r", origin)
            raise web.HTTPForbidden()
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        q = server.hub.subscribe()
        await ws.send_str(
            json.dumps(
                {
                    "type": "snapshot",
                    "stats": server.stats.snapshot(),
                    "decisions": server.latest_decisions,
                    "log": server.recent_log,
                    "run": server.current_run,
                    "runs": server.run_history,
                }
            )
        )

        async def pump() -> None:
            try:
                while True:
                    msg = await q.get()
                    if not server.hub.is_subscribed(q):
                        break  # dropped by the hub for falling behind
                    await ws.send_str(json.dumps(msg))
            except (ConnectionResetError, RuntimeError):
                pass
            finally:
                await ws.close()

        pump_task = asyncio.create_task(pump())
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("type") == "control":
                    await server.send_control(bool(data.get("automation", True)))
        finally:
            server.hub.unsubscribe(q)
            pump_task.cancel()
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    return app


async def run_dashboard(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    log.info("dashboard at http://%s:%d/", host, port)
    return runner

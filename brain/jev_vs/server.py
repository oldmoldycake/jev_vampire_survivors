"""TCP server the game plugin connects to. One connection at a time is expected."""

from __future__ import annotations

import asyncio
import logging
import time

from . import protocol
from .config import Config
from .decide import Decider, Decision
from .hub import Hub
from .questions import VARIETY_KINDS
from .runlog import RunLog
from .stats import Stats

log = logging.getLogger(__name__)

PICK_EVENTS = {
    "character_select": "character",
    "stage_select": "stage",
    "level_up": "level_up",
    "weapon_select": "weapon_select",
    "arcana_select": "arcana_select",
}
RECENT_HISTORY_LIMIT = 5


def _recent_values(history: list[dict], key: str, limit: int = RECENT_HISTORY_LIMIT) -> list[str]:
    """Last `limit` non-empty values of `key` from finished-run summaries, most recent first."""
    out: list[str] = []
    for run in reversed(history):
        value = run.get(key)
        if value:
            out.append(value)
            if len(out) >= limit:
                break
    return out


class PluginServer:
    def __init__(self, config: Config, decider: Decider, runlog: RunLog, hub: Hub, stats: Stats):
        self.config = config
        self.decider = decider
        self.runlog = runlog
        self.hub = hub
        self.stats = stats
        self._server: asyncio.AbstractServer | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._in_flight = False
        self._tasks: set[asyncio.Task] = set()
        self.last_direction: dict | None = None
        self.latest_decisions: dict[str, dict] = {}
        self.recent_log: list[dict] = []
        self.current_run: dict = {}
        self.run_history: list[dict] = []

    # ------------------------------------------------------------ lifecycle
    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.config.plugin_host, self.config.plugin_port)
        log.info("plugin server listening on %s:%d", self.config.plugin_host, self.port)
        return self.port

    async def stop(self) -> None:
        if self._writer is not None:
            self._writer.close()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    # ------------------------------------------------------------ helpers
    def _note(self, text: str, **extra) -> None:
        entry = {"t": time.time(), "text": text, **extra}
        self.recent_log.append(entry)
        del self.recent_log[:-50]
        self.hub.publish({"type": "event", **entry})

    def _publish_stats(self) -> None:
        self.hub.publish({"type": "stats", **self.stats.snapshot()})

    async def _reply(self, writer: asyncio.StreamWriter, msg: dict) -> None:
        try:
            writer.write(protocol.encode(msg))
            await writer.drain()
        except (ConnectionError, RuntimeError) as e:
            log.warning("reply failed: %s", e)

    async def send_control(self, automation: bool) -> bool:
        if self._writer is None or self._writer.is_closing():
            return False
        await self._reply(self._writer, protocol.control(automation))
        self._note(f"automation {'resumed' if automation else 'paused'} from dashboard")
        return True

    def _record_decision(self, d: Decision, **extra) -> dict:
        payload = {"type": "decision", **d.to_dict(), **extra}
        self.latest_decisions[d.kind] = payload
        self.stats.record(d)
        self.hub.publish(payload)
        self._publish_stats()
        return payload

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.exception("handler task failed", exc_info=task.exception())

    # ------------------------------------------------------------ connection
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info("plugin connected from %s", peer)
        self._writer = writer
        self.stats.set_plugin_connected(True)
        self._publish_stats()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = protocol.decode(line)
                except protocol.ProtocolError as e:
                    log.warning("skipping bad line: %s", e)
                    continue
                await self._dispatch(msg, writer)
        except (ConnectionError, asyncio.IncompleteReadError) as e:
            log.info("plugin connection error: %s", e)
        finally:
            log.info("plugin disconnected")
            if self._writer is writer:
                self._writer = None
            self.stats.set_plugin_connected(False)
            self._publish_stats()
            writer.close()

    async def _dispatch(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        t = msg["type"]
        if t == "hello":
            self._note(f"plugin hello: game {msg.get('game_version')} plugin {msg.get('plugin_version')}")
        elif t == "tick":
            self._spawn(self._on_tick(msg, writer))
        elif t == "event":
            self._spawn(self._on_event(msg, writer))
        else:
            log.warning("unknown message type %r", t)

    async def _on_tick(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        mid = msg.get("id", 0)
        if self._in_flight:
            self.stats.mark_reused()
            last = self.last_direction
            reply = protocol.move_reply(
                mid,
                last["choice"] if last else "stay",
                last["probabilities"] if last else {"stay": 1.0},
                last["confidence"] if last else 0.0,
                "reused",
            )
            await self._reply(writer, reply)
            return
        self._in_flight = True
        try:
            state = msg.get("state", {})
            digest, decision = await self.decider.direction(state)
            reply = protocol.move_reply(
                mid, decision.choice, decision.probabilities, decision.confidence, decision.source
            )
            self.last_direction = reply
            await self._reply(writer, reply)
            entities = {k: state.get(k, []) for k in ("enemies", "gems", "pickups")}
            entities["screen"] = state.get("screen", {})
            self._record_decision(decision, digest=digest.to_dict(), entities=entities, t=msg.get("t"))
            self.runlog.tick(
                {"id": mid, "t": msg.get("t"), "state": state, "digest": digest.to_dict(), **decision.to_dict()}
            )
        finally:
            self._in_flight = False

    async def _on_event(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        mid = msg.get("id", 0)
        event = str(msg.get("event", ""))
        if event == "game_over":
            await self._reply(writer, protocol.noop_reply(mid))
            summary = msg.get("summary", {})
            self.runlog.event({"id": mid, "event": event, "summary": summary})
            snap = self.stats.snapshot()  # spec section 9 run stats, taken before the run log closes
            written = self.runlog.end_run(
                {
                    **summary,
                    "jev_calls": snap["jev_calls"],
                    "fallback_calls": snap["fallback_calls"],
                    "reused": snap["reused"],
                    "avg_latency_ms": snap["avg_latency_ms"],
                    "input_tokens": snap["input_tokens"],
                    "cost_usd": snap["cost_usd"],
                }
            )
            if written:  # a game_over with no active run must not add a row
                self.run_history.append(written)
                del self.run_history[:-50]
            self._note(
                f"game over: {summary.get('character')} on {summary.get('stage')} "
                f"survived {summary.get('seconds')}s level {summary.get('level')}"
            )
            self.hub.publish({"type": "run", "phase": "end", "summary": written})
            self.current_run = {}
            return
        kind = PICK_EVENTS.get(event)
        if kind is None:
            log.warning("unknown event %r", event)
            await self._reply(writer, protocol.noop_reply(mid))
            return
        options = list(msg.get("options", []))
        # No options means no pick and no run can start, so no run log opens either (ruling 2026-09-18).
        if not options:
            await self._reply(writer, protocol.noop_reply(mid))
            self._note(f"{event} with no options; noop")
            return
        if event == "character_select":
            self.stats.reset_run()
            self.decider.reset_run()
            self.runlog.start_run({})
            self.current_run = {"started_at": time.time()}
            self.hub.publish({"type": "run", "phase": "start", "meta": self.current_run})
        recent = _recent_values(self.run_history, kind) if kind in VARIETY_KINDS else None
        decision = await self.decider.pick(kind, options, msg.get("build"), recent=recent)
        chosen = options[decision.index]
        reply_index = chosen.get("index", decision.index)
        await self._reply(
            writer,
            protocol.pick_reply(
                mid, reply_index, decision.choice, decision.probabilities, decision.confidence, decision.source
            ),
        )
        if event == "character_select":
            self.current_run["character"] = chosen.get("id")
            self.runlog.update_meta(character=chosen.get("id"))
        elif event == "stage_select":
            self.current_run["stage"] = chosen.get("id")
            self.runlog.update_meta(stage=chosen.get("id"))
        self._record_decision(decision, options=options)
        self.runlog.event({"id": mid, "event": event, "options": options, **decision.to_dict()})
        self._note(
            f"{event}: picked {chosen.get('name', chosen.get('id'))} "
            f"({decision.source}, conf {decision.confidence:.2f})"
        )

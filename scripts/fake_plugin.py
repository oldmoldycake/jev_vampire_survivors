#!/usr/bin/env python3
"""Pretend to be the game plugin. Usage:

  uv run --project brain python scripts/fake_plugin.py --ticks 20 --hz 4
  uv run --project brain python scripts/fake_plugin.py --replay brain/runs/20260917-220000

Prints each reply. Needs a running brain (uv run --project brain jev-vs).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
from pathlib import Path


def synthetic_state(i: int) -> dict:
    ang = i * 0.3
    enemies = [{"x": 3 * math.cos(ang + k), "y": 3 * math.sin(ang + k), "hp": 10, "type": "BAT", "boss": False} for k in range(6)]
    gems = [{"x": random.uniform(-4, 4), "y": random.uniform(-3, 3), "value": 1} for _ in range(5)]
    return {
        "player": {"x": 0, "y": 0, "hp": 60 + 20 * math.sin(i / 5), "max_hp": 100, "level": 1 + i // 10, "xp": 5,
                   "xp_to_next": 30, "minute": i // 240, "seconds": i / 4, "character": "ANTONIO",
                   "weapons": [{"id": "WHIP", "level": 2, "max": False}], "passives": []},
        "enemies": enemies, "gems": gems, "pickups": [], "screen": {"half_w": 8.0, "half_h": 4.5},
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=48231)
    ap.add_argument("--ticks", type=int, default=20)
    ap.add_argument("--hz", type=float, default=4.0)
    ap.add_argument("--replay", type=Path, default=None)
    args = ap.parse_args()

    reader, writer = await asyncio.open_connection(args.host, args.port)
    mid = 0

    async def send(msg: dict) -> dict | None:
        nonlocal mid
        if "id" not in msg and msg["type"] != "hello":
            mid += 1
            msg["id"] = mid
        writer.write((json.dumps(msg) + "\n").encode())
        await writer.drain()
        if msg["type"] == "hello":
            return None
        reply = json.loads(await asyncio.wait_for(reader.readline(), 5))
        print(json.dumps(reply))
        return reply

    await send({"type": "hello", "game_version": "fake", "plugin_version": "fake"})
    await send({"type": "event", "event": "character_select", "options": [
        {"id": "ANTONIO", "name": "Antonio Belpaese", "description": "Gains 10% more damage every 10 levels.", "starting_weapon": "WHIP"},
        {"id": "IMELDA", "name": "Imelda Belpaese", "description": "Gains 10% more experience every 5 levels.", "starting_weapon": "MAGIC_MISSILE"},
    ]})
    await send({"type": "event", "event": "stage_select", "options": [
        {"id": "FOREST", "name": "Mad Forest", "description": "The Castle is a lie, but there's plenty of things to do."},
        {"id": "LIBRARY", "name": "Inlaid Library", "description": "Corridors, few open spaces."},
    ]})
    states = [synthetic_state(i) for i in range(args.ticks)]
    if args.replay:
        states = [json.loads(l)["state"] for l in (args.replay / "ticks.jsonl").read_text().splitlines()]
    for i, st in enumerate(states):
        await send({"type": "tick", "t": i / args.hz, "state": st})
        await asyncio.sleep(1.0 / args.hz)
        if i == len(states) // 2:
            await send({"type": "event", "event": "level_up", "options": [
                {"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 3, "is_new": False, "description": "Attacks horizontally, passes through enemies."},
                {"index": 1, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 1, "is_new": True, "description": "Raises inflicted damage by 10%."},
            ], "build": {"weapons": ["WHIP L2"], "passives": [], "level": 2, "minute": 0}})
    await send({"type": "event", "event": "game_over", "summary": {"character": "ANTONIO", "stage": "FOREST", "seconds": len(states) / args.hz, "level": 3, "kills": 40, "stage_complete": False}})
    writer.close()


if __name__ == "__main__":
    asyncio.run(main())

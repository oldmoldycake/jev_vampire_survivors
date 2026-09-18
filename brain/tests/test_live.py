"""Real API calls. Run with:  TYPESAFE_API_KEY=... uv run pytest -m live -v"""

import json
import os
import time
from pathlib import Path

import pytest

from jev_vs.decide import Decider
from jev_vs.jev_client import JevClient
from jev_vs.questions import DEFAULT_THRESHOLDS, DIRECTIONS
from tests.conftest import enemy, gem, make_state

pytestmark = pytest.mark.live
needs_key = pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="TYPESAFE_API_KEY not set")


def _states() -> list[dict]:
    runs = sorted(Path("runs").glob("*/ticks.jsonl"))
    if runs:
        lines = runs[-1].read_text().splitlines()[:8]
        return [json.loads(line)["state"] for line in lines]
    return [
        make_state(enemies=[enemy(0, 0.3), enemy(0.2, 0.4), enemy(-0.1, 0.5)], gems=[gem(0, -1.5)], hp=30),
        make_state(gems=[gem(2, 0), gem(2.2, 0.1)], hp=95),
        make_state(),
    ]


@needs_key
async def test_direction_answers_are_well_formed_and_fast():
    jev = JevClient(model="jev-latest", timeout_s=2.0, max_retries=1)
    dec = Decider(jev, DEFAULT_THRESHOLDS)
    try:
        for st in _states():
            t0 = time.perf_counter()
            _, d = await dec.direction(st)
            assert d.source == "jev", "live call fell back"
            assert d.choice in DIRECTIONS
            assert abs(sum(d.probabilities.values()) - 1.0) < 0.02
            assert 0.0 <= d.confidence <= 1.0
            assert (time.perf_counter() - t0) < 2.0
    finally:
        await jev.aclose()


@needs_key
async def test_danger_north_with_low_hp_does_not_walk_north():
    jev = JevClient(model="jev-latest", timeout_s=2.0, max_retries=1)
    dec = Decider(jev, DEFAULT_THRESHOLDS)
    try:
        st = make_state(enemies=[enemy(0, 0.3), enemy(0.2, 0.4), enemy(-0.1, 0.5), enemy(0, 0.6)], hp=15)
        _, d = await dec.direction(st)
        assert d.choice not in ("north", "north_east", "north_west")
    finally:
        await jev.aclose()


@needs_key
async def test_level_up_prefers_owned_weapon_over_random_new_item():
    jev = JevClient(model="jev-latest", timeout_s=2.0, max_retries=1)
    dec = Decider(jev, DEFAULT_THRESHOLDS)
    try:
        opts = [
            {
                "index": 0,
                "id": "SKULL_O_MANIAC",
                "name": "Skull O'Maniac",
                "kind": "passive",
                "level": 1,
                "is_new": True,
                "description": "Increases enemy speed, health, quantity and frequency.",
            },
            {
                "index": 1,
                "id": "WHIP",
                "name": "Whip",
                "kind": "weapon",
                "level": 4,
                "is_new": False,
                "description": "Attacks horizontally, passes through enemies. Fires one more projectile.",
            },
        ]
        d = await dec.pick("level_up", opts, {"weapons": ["WHIP L3"], "passives": [], "level": 4, "minute": 2})
        assert d.source == "jev" and d.choice == "WHIP"
    finally:
        await jev.aclose()

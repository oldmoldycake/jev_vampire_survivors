import logging
import random

import pytest

from jev_vs import decide
from jev_vs.digest import digest_state
from jev_vs.questions import DEFAULT_THRESHOLDS as TH
from tests.conftest import FakeJev, enemy, gem, make_state


async def test_direction_uses_jev_answer():
    fake = FakeJev(script={"direction": ("south", {"south": 0.7, "north": 0.3}, 0.5)})
    dec = decide.Decider(fake, TH)
    d, decision = await dec.direction(make_state())
    assert decision.kind == "direction"
    assert decision.choice == "south" and decision.index == 4
    assert decision.source == "jev"
    assert decision.probabilities["south"] == 0.7
    assert decision.latency_ms == 12.0
    assert decision.input_tokens == 100
    assert len(fake.calls) == 1


async def test_direction_falls_back_when_jev_fails():
    fake = FakeJev(fail=True)
    dec = decide.Decider(fake, TH)
    st = make_state(enemies=[enemy(0, 0.3), enemy(0, 0.4)], gems=[gem(0, -1)])
    _, decision = await dec.direction(st)
    assert decision.source == "fallback"
    assert decision.choice == "south"
    assert decision.probabilities[decision.choice] == 1.0
    assert decision.confidence == 0.0


async def test_direction_rejects_unknown_choice_with_fallback():
    fake = FakeJev(script={"direction": ("sideways", {"sideways": 1.0}, 0.9)})
    dec = decide.Decider(fake, TH)
    _, decision = await dec.direction(make_state())
    assert decision.source == "fallback"
    assert decision.choice in decide.DIRECTIONS


def test_fallback_direction_prefers_least_pressure_then_gems():
    st = make_state(enemies=[enemy(0, 0.3)] * 3 + [enemy(1, 0)], gems=[gem(-1, 0), gem(-1.2, 0)])
    d = digest_state(st, TH)
    assert decide.fallback_direction(d) == "west"


def test_fallback_direction_stays_when_all_quiet():
    assert decide.fallback_direction(digest_state(make_state(), TH)) == "stay"


async def test_pick_maps_choice_to_index():
    opts = [
        {"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 5},
        {"index": 1, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 2},
    ]
    fake = FakeJev(script={"level_up": ("SPINACH", {"SPINACH": 0.8, "WHIP": 0.2}, 0.6)})
    dec = decide.Decider(fake, TH)
    decision = await dec.pick("level_up", opts, {"weapons": ["WHIP L4"], "passives": []})
    assert decision.index == 1 and decision.choice == "SPINACH" and decision.source == "jev"
    assert decision.labels["SPINACH"] == "Spinach"


async def test_pick_falls_back_to_first_option():
    opts = [{"index": 0, "id": "A", "name": "A"}, {"index": 1, "id": "B", "name": "B"}]
    dec = decide.Decider(FakeJev(fail=True), TH)
    decision = await dec.pick("character", opts)
    assert decision.index == 0 and decision.choice == "A" and decision.source == "fallback"


async def test_pick_with_no_options_raises():
    dec = decide.Decider(FakeJev(), TH)
    with pytest.raises(ValueError):
        await dec.pick("stage", [])


async def test_jev_client_constructs_without_api_key(monkeypatch):
    from jev_vs.jev_client import JevClient
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    client = JevClient(model="jev-latest", timeout_s=0.5, max_retries=0)   # must not raise
    await client.aclose()                                                   # must not raise


async def test_real_jev_client_falls_back_end_to_end_without_api_key(monkeypatch):
    # Offline-safe: AsyncTypeSafeClient raises for a missing API key during construction,
    # before any network call is made, so Decider.direction still falls back cleanly.
    from jev_vs.jev_client import JevClient
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    dec = decide.Decider(JevClient(model="jev-latest", timeout_s=0.5, max_retries=0), TH)
    _, d = await dec.direction(make_state())
    assert d.source == "fallback"
    await dec.jev.aclose()


async def test_pick_character_samples_but_never_below_sample_floor():
    opts = [
        {"index": 0, "id": "A", "name": "A"},
        {"index": 1, "id": "B", "name": "B"},
        {"index": 2, "id": "C", "name": "C"},
    ]
    fake = FakeJev(script={"character": ("A", {"A": 0.6, "B": 0.39, "C": 0.01}, 0.9)})
    dec = decide.Decider(fake, TH, rng=random.Random(1234))
    seen = set()
    for _ in range(300):
        decision = await dec.pick("character", opts)
        assert decision.choice in {"A", "B", "C"}   # always a valid option
        assert decision.source == "jev"
        assert decision.sampled is True
        seen.add(decision.choice)
    assert "C" not in seen   # C's 1% probability is below SAMPLE_FLOOR (5%) and is never chosen
    assert seen.issubset({"A", "B"})


async def test_pick_level_up_always_returns_jevs_top_answer():
    opts = [
        {"index": 0, "id": "WHIP", "name": "Whip", "kind": "weapon", "level": 5},
        {"index": 1, "id": "SPINACH", "name": "Spinach", "kind": "passive", "level": 2},
    ]
    fake = FakeJev(script={"level_up": ("SPINACH", {"SPINACH": 0.55, "WHIP": 0.45}, 0.6)})
    dec = decide.Decider(fake, TH, rng=random.Random(0))
    for _ in range(20):
        decision = await dec.pick("level_up", opts, {"weapons": [], "passives": []})
        assert decision.choice == "SPINACH"
        assert decision.sampled is False


async def test_fallback_warnings_are_rate_limited(caplog):
    caplog.set_level(logging.DEBUG, logger="jev_vs.decide")
    fake = FakeJev(fail=True)
    dec = decide.Decider(fake, TH)
    for _ in range(5):
        await dec.direction(make_state())
    warnings = [r for r in caplog.records if r.name == "jev_vs.decide" and r.levelno == logging.WARNING]
    debugs = [r for r in caplog.records if r.name == "jev_vs.decide" and r.levelno == logging.DEBUG]
    assert len(warnings) == 1
    assert len(debugs) == 4

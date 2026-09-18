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

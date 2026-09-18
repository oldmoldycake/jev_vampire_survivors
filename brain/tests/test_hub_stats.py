import asyncio

from jev_vs.decide import Decision
from jev_vs.hub import Hub
from jev_vs.stats import Stats


async def test_hub_fans_out_and_drops_full_clients():
    hub = Hub(maxsize=2)
    fast = hub.subscribe()
    slow = hub.subscribe()
    assert hub.publish({"n": 1}) == 0
    await fast.get()
    assert hub.publish({"n": 2}) == 0
    await fast.get()
    dropped = hub.publish({"n": 3})  # slow now has 3 pending -> over maxsize 2
    assert dropped == 1
    assert hub.client_count == 1
    assert (await fast.get()) == {"n": 3}
    hub.unsubscribe(fast)
    assert hub.client_count == 0
    assert isinstance(slow, asyncio.Queue)


def _decision(source="jev", latency=100.0, tokens=1000):
    return Decision(
        kind="direction",
        choice="north",
        index=0,
        probabilities={"north": 1.0},
        confidence=0.5,
        latency_ms=latency,
        source=source,
        input_tokens=tokens,
    )


def test_stats_counts_and_cost():
    s = Stats()
    s.record(_decision(latency=100.0, tokens=1_000_000))
    s.record(_decision(source="fallback", latency=0.0, tokens=0))
    s.record(_decision(latency=300.0, tokens=1_000_000))
    s.mark_reused()
    snap = s.snapshot()
    assert snap["calls"] == 3 and snap["jev_calls"] == 2 and snap["fallback_calls"] == 1 and snap["reused"] == 1
    assert snap["last_latency_ms"] == 300.0
    assert snap["avg_latency_ms"] == 200.0
    assert snap["input_tokens"] == 2_000_000
    assert abs(snap["cost_usd"] - 0.084) < 1e-9
    assert snap["plugin_connected"] is False
    s.set_plugin_connected(True)
    assert s.snapshot()["plugin_connected"] is True
    s.reset_run()
    assert s.snapshot()["calls"] == 0

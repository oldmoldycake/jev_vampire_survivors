"""Per-run counters shown in the dashboard header."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .decide import Decision

USD_PER_MILLION_INPUT_TOKENS = 0.042


@dataclass
class Stats:
    calls: int = 0
    jev_calls: int = 0
    fallback_calls: int = 0
    reused: int = 0
    last_latency_ms: float = 0.0
    input_tokens: int = 0
    plugin_connected: bool = False
    jev_ok: bool = True
    run_started_at: float = field(default_factory=time.time)
    _latency_sum: float = 0.0

    def record(self, d: Decision) -> None:
        self.calls += 1
        if d.source == "jev":
            self.jev_calls += 1
            self.jev_ok = True
            self.last_latency_ms = d.latency_ms
            self._latency_sum += d.latency_ms
        else:
            self.fallback_calls += 1
            self.jev_ok = False
        self.input_tokens += d.input_tokens

    def mark_reused(self) -> None:
        self.reused += 1

    def set_plugin_connected(self, connected: bool) -> None:
        self.plugin_connected = connected

    def reset_run(self) -> None:
        self.calls = self.jev_calls = self.fallback_calls = self.reused = 0
        self.last_latency_ms = 0.0
        self.input_tokens = 0
        self._latency_sum = 0.0
        self.run_started_at = time.time()

    def snapshot(self) -> dict:
        elapsed_h = max(time.time() - self.run_started_at, 1e-6) / 3600.0
        cost = self.input_tokens / 1e6 * USD_PER_MILLION_INPUT_TOKENS
        return {
            "calls": self.calls,
            "jev_calls": self.jev_calls,
            "fallback_calls": self.fallback_calls,
            "reused": self.reused,
            "last_latency_ms": round(self.last_latency_ms, 1),
            "avg_latency_ms": round(self._latency_sum / self.jev_calls, 1) if self.jev_calls else 0.0,
            "input_tokens": self.input_tokens,
            "cost_usd": round(cost, 6),
            "cost_per_hour_usd": round(cost / elapsed_h, 4),
            "plugin_connected": self.plugin_connected,
            "jev_ok": self.jev_ok,
            "run_started_at": self.run_started_at,
        }

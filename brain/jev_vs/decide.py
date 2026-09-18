"""Decider: digest -> Ask -> Jev -> Decision, with heuristic fallbacks."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .digest import Digest, digest_state
from .questions import DIRECTIONS, Ask, Thresholds, direction_question, options_question

log = logging.getLogger(__name__)

_PRESSURE_RANK = {"none": 0, "light": 1, "moderate": 2, "heavy": 3}
_GEM_RANK = {"none": 0, "few": 1, "many": 2}


@dataclass
class Decision:
    kind: str
    choice: str
    index: int
    probabilities: dict[str, float]
    confidence: float
    latency_ms: float
    source: str                       # "jev" | "fallback"
    input_tokens: int = 0
    instructions: str = ""
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "choice": self.choice, "index": self.index,
            "probabilities": self.probabilities, "confidence": self.confidence,
            "latency_ms": round(self.latency_ms, 1), "source": self.source,
            "input_tokens": self.input_tokens, "instructions": self.instructions, "labels": self.labels,
        }


def fallback_direction(d: Digest) -> str:
    """Least pressure wins; ties broken by most gems; all quiet means stay."""
    best = None
    for name in DIRECTIONS[:-1]:
        s = d.sectors[name]
        key = (_PRESSURE_RANK[s.pressure], -_GEM_RANK[s.gems], -s.gem_count)
        if best is None or key < best[0]:
            best = (key, name)
    assert best is not None
    if best[0][0] == 0 and best[0][1] == 0:
        return "stay"
    return best[1]


def fallback_pick(options: list[dict]) -> int:
    return 0


class Decider:
    def __init__(self, jev, thresholds: Thresholds):
        self._jev = jev
        self._th = thresholds

    @property
    def jev(self):
        """The Jev client this decider asks; exposed so the process can close it at shutdown."""
        return self._jev

    async def _ask(self, ask: Ask) -> tuple[str | None, dict, float, float, int]:
        """Returns (choice or None on failure, probabilities, confidence, latency_ms, tokens)."""
        try:
            result = await self._jev.ask(ask.state, {ask.name: ask.question})
        except Exception as e:  # any SDK/network error becomes a fallback, never a crash
            log.warning("jev %s failed: %s", ask.name, e)
            return None, {}, 0.0, 0.0, 0
        pick = result.answers.get(ask.name)
        if pick is None or pick.choice not in ask.keys:
            log.warning("jev %s returned unusable choice %r", ask.name, getattr(pick, "choice", None))
            return None, {}, 0.0, result.latency_ms, result.input_tokens
        return pick.choice, pick.probabilities, pick.confidence, result.latency_ms, result.input_tokens

    async def direction(self, state: dict) -> tuple[Digest, Decision]:
        d = digest_state(state, self._th)
        ask = direction_question(d)
        choice, probs, conf, latency, tokens = await self._ask(ask)
        source = "jev"
        if choice is None:
            choice, probs, conf, source = fallback_direction(d), {}, 0.0, "fallback"
            probs = {k: (1.0 if k == choice else 0.0) for k in ask.keys}
        return d, Decision(
            kind="direction", choice=choice, index=ask.keys.index(choice), probabilities=probs,
            confidence=conf, latency_ms=latency, source=source, input_tokens=tokens,
            instructions=ask.instructions, labels=ask.labels,
        )

    async def pick(self, kind: str, options: list[dict], build: dict | None = None) -> Decision:
        if not options:
            raise ValueError(f"{kind}: no options to pick from")
        ask = options_question(kind, options, build)
        choice, probs, conf, latency, tokens = await self._ask(ask)
        source = "jev"
        if choice is None:
            idx = fallback_pick(options)
            choice, conf, source = ask.keys[idx], 0.0, "fallback"
            probs = {k: (1.0 if k == choice else 0.0) for k in ask.keys}
        return Decision(
            kind=kind, choice=choice, index=ask.keys.index(choice), probabilities=probs,
            confidence=conf, latency_ms=latency, source=source, input_tokens=tokens,
            instructions=ask.instructions, labels=ask.labels,
        )

"""Decider: digest -> Ask -> Jev -> Decision, with heuristic fallbacks."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

from .digest import BlockMemory, Digest, digest_state
from .questions import DIRECTIONS, VARIETY_KINDS, Ask, Thresholds, direction_question, options_question

log = logging.getLogger(__name__)

_PRESSURE_RANK = {"none": 0, "light": 1, "moderate": 2, "heavy": 3}
_GEM_RANK = {"none": 0, "few": 1, "many": 2}

WARN_INTERVAL_S = 60.0  # rate limit for fallback-failure warnings; see Decider._log_failure

# character and stage picks are sampled (not always Jev's top answer) so a human doesn't see the
# same character and stage every run; options below this probability are never sampled.
SAMPLE_FLOOR = 0.05


@dataclass
class Decision:
    kind: str
    choice: str
    index: int
    probabilities: dict[str, float]
    confidence: float
    latency_ms: float
    source: str  # "jev" | "human" | "fallback"
    input_tokens: int = 0
    instructions: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    sampled: bool = False  # True when the choice came from the variety sampler, not Jev's raw top answer

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "choice": self.choice,
            "index": self.index,
            "probabilities": self.probabilities,
            "confidence": self.confidence,
            "latency_ms": round(self.latency_ms, 1),
            "source": self.source,
            "input_tokens": self.input_tokens,
            "instructions": self.instructions,
            "labels": self.labels,
            "sampled": self.sampled,
        }


def fallback_direction(d: Digest) -> str:
    """Least pressure wins among unblocked sectors; ties broken by most gems; all quiet, or every
    compass sector blocked, means stay."""
    best = None
    for name in DIRECTIONS[:-1]:
        s = d.sectors[name]
        if s.blocked:
            continue
        key = (_PRESSURE_RANK[s.pressure], -_GEM_RANK[s.gems], -s.gem_count)
        if best is None or key < best[0]:
            best = (key, name)
    if best is None:
        return "stay"
    if best[0][0] == 0 and best[0][1] == 0:
        return "stay"
    return best[1]


def fallback_pick(options: list[dict]) -> int:
    return 0


class Decider:
    def __init__(self, jev, thresholds: Thresholds, rng: random.Random | None = None):
        self._jev = jev
        self._th = thresholds
        self._rng = rng if rng is not None else random.Random()
        self._block_memory = BlockMemory(thresholds)
        self._failures_since_warn = 0
        self._last_warned = 0.0

    @property
    def jev(self):
        """The Jev client this decider asks; exposed so the process can close it at shutdown."""
        return self._jev

    def reset_run(self) -> None:
        """Forget remembered blocks and the stuck trail; call at the start of a new run."""
        self._block_memory.clear()

    def _log_failure(self, msg: str, *args) -> None:
        """Warn at most once every WARN_INTERVAL_S; every other failure just logs at DEBUG."""
        self._failures_since_warn += 1
        now = time.time()
        if now - self._last_warned >= WARN_INTERVAL_S:
            log.warning(msg + " (%d failure(s) since last warning)", *args, self._failures_since_warn)
            self._last_warned = now
            self._failures_since_warn = 0
        else:
            log.debug(msg, *args)

    async def _ask(self, ask: Ask) -> tuple[str | None, dict, float, float, int]:
        """Returns (choice or None on failure, probabilities, confidence, latency_ms, tokens)."""
        try:
            result = await self._jev.ask(ask.state, {ask.name: ask.question})
        except Exception as e:  # any SDK/network error becomes a fallback, never a crash
            self._log_failure("jev %s failed: %s", ask.name, e)
            return None, {}, 0.0, 0.0, 0
        pick = result.answers.get(ask.name)
        if pick is None or pick.choice not in ask.keys:
            self._log_failure("jev %s returned unusable choice %r", ask.name, getattr(pick, "choice", None))
            return None, {}, 0.0, result.latency_ms, result.input_tokens
        return pick.choice, pick.probabilities, pick.confidence, result.latency_ms, result.input_tokens

    async def direction(self, state: dict) -> tuple[Digest, Decision]:
        d = digest_state(state, self._th, memory=self._block_memory)
        ask = direction_question(d)
        choice, probs, conf, latency, tokens = await self._ask(ask)
        source = "jev"
        if choice is None:
            choice, probs, conf, source = fallback_direction(d), {}, 0.0, "fallback"
            probs = {k: (1.0 if k == choice else 0.0) for k in ask.keys}
        return d, Decision(
            kind="direction",
            choice=choice,
            index=ask.keys.index(choice),
            probabilities=probs,
            confidence=conf,
            latency_ms=latency,
            source=source,
            input_tokens=tokens,
            instructions=ask.instructions,
            labels=ask.labels,
        )

    def _sample_choice(self, probs: dict[str, float], keys: list[str]) -> str | None:
        """Drop options below SAMPLE_FLOOR, renormalise, and sample one; None if nothing survives."""
        candidates = [(k, probs.get(k, 0.0)) for k in keys if probs.get(k, 0.0) >= SAMPLE_FLOOR]
        total = sum(p for _, p in candidates)
        if not candidates or total <= 0:
            return None
        r = self._rng.random() * total
        upto = 0.0
        for k, p in candidates:
            upto += p
            if r <= upto:
                return k
        return candidates[-1][0]  # floating-point rounding fallback

    async def pick(
        self,
        kind: str,
        options: list[dict],
        build: dict | None = None,
        recent: list[str] | None = None,
        pinned_index: int | None = None,
    ) -> Decision:
        """Choose one option. `pinned_index`'s contract is "this index is offered, use it" —
        whether a human's pin is honourable for this menu is decided in server.py, which has
        the options and the event log (spec section 3.3)."""
        if not options:
            raise ValueError(f"{kind}: no options to pick from")
        ask = options_question(kind, options, build, recent=recent)
        if pinned_index is not None:
            # A human already decided. The Ask above is pure and the dashboard card needs its
            # labels, but asking Jev would spend money and menu latency to confirm a foregone
            # conclusion, so we don't; variety sampling is bypassed by construction.
            choice = ask.keys[pinned_index]
            return Decision(
                kind=kind,
                choice=choice,
                index=pinned_index,
                probabilities={choice: 1.0},
                confidence=1.0,
                latency_ms=0.0,
                source="human",
                input_tokens=0,
                instructions=ask.instructions,
                labels=ask.labels,
            )
        choice, probs, conf, latency, tokens = await self._ask(ask)
        source = "jev"
        sampled = False
        if choice is None:
            idx = fallback_pick(options)
            choice, conf, source = ask.keys[idx], 0.0, "fallback"
            probs = {k: (1.0 if k == choice else 0.0) for k in ask.keys}
        elif kind in VARIETY_KINDS:
            picked = self._sample_choice(probs, ask.keys)
            if picked is not None:
                choice = picked
                sampled = True
        return Decision(
            kind=kind,
            choice=choice,
            index=ask.keys.index(choice),
            probabilities=probs,
            confidence=conf,
            latency_ms=latency,
            source=source,
            input_tokens=tokens,
            instructions=ask.instructions,
            labels=ask.labels,
            sampled=sampled,
        )

"""Thin wrapper over the TypeSafe SDK so the rest of the brain never sees SDK types."""
from __future__ import annotations

import time
from dataclasses import dataclass

from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy


@dataclass(frozen=True)
class ChoicePick:
    choice: str
    probabilities: dict[str, float]
    confidence: float


@dataclass(frozen=True)
class JevResult:
    answers: dict[str, ChoicePick]
    latency_ms: float
    input_tokens: int


class JevClient:
    """Async client. `ask` raises on any API failure; callers decide what to do."""

    def __init__(self, *, model: str, timeout_s: float, max_retries: int, api_key: str | None = None):
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._client: AsyncTypeSafeClient | None = None

    async def ask(self, state: dict | str | list, questions: dict[str, Choice]) -> JevResult:
        if self._client is None:
            self._client = AsyncTypeSafeClient(
                api_key=self._api_key,
                model=self._model,
                retry=RetryPolicy(max_retries=self._max_retries, backoff_initial=0.05, backoff_max=0.2, timeout=self._timeout_s),
                timeout=self._timeout_s,
            )

        t0 = time.perf_counter()
        resp = await self._client.system_one(state, questions)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        answers: dict[str, ChoicePick] = {}
        for name, ans in resp.answers.items():
            answers[name] = ChoicePick(
                choice=str(ans.choice),
                probabilities={str(k): float(v) for k, v in dict(ans.probabilities).items()},
                confidence=float(ans.confidence),
            )
        tokens = int(getattr(resp.usage, "input_tokens", 0) or 0)
        return JevResult(answers=answers, latency_ms=latency_ms, input_tokens=tokens)

    async def aclose(self) -> None:
        if self._client is None:
            return
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result

"""Fan-out of dashboard messages. A client that cannot keep up is dropped, never awaited."""
from __future__ import annotations

import asyncio


class Hub:
    def __init__(self, maxsize: int = 64):
        self._maxsize = maxsize
        self._clients: set[asyncio.Queue] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    def publish(self, msg: dict) -> int:
        dropped = 0
        for q in list(self._clients):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                self._clients.discard(q)
                dropped += 1
        return dropped

    def is_subscribed(self, q: asyncio.Queue) -> bool:
        return q in self._clients

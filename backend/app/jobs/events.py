"""In-process event bus feeding the Server-Sent Events stream. Thread-safe publish from job threads."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()
        self.recent: deque[dict[str, Any]] = deque(maxlen=200)
        self._seq = 0

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = [(l, x) for l, x in self._subs if x is not q]

    def publish(self, kind: str, data: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._seq += 1
            ev = {"id": self._seq, "type": kind, "ts": time.time(), "data": data or {}}
            self.recent.append(ev)
            subs = list(self._subs)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(_put, q, ev)
            except RuntimeError:
                pass


def _put(q: asyncio.Queue, ev: dict[str, Any]) -> None:
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(ev)


def sse_format(ev: dict[str, Any]) -> str:
    return f"id: {ev['id']}\nevent: {ev['type']}\ndata: {json.dumps(ev, default=str)}\n\n"


bus = EventBus()

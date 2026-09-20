"""A tiny in-process pub/sub broker for Server-Sent Events.

There is no message queue in this stack (no Redis, no Postgres LISTEN/NOTIFY
wiring), and adding one is out of scope for a hackathon prototype. This gives
every connected browser tab a live feed of what the API just did — a site
created, a dataset processed, a validation run, a review decision — using
nothing but an asyncio.Queue per subscriber. It only fans out events that
happened in *this* server process; if you run multiple API workers, each
worker's subscribers only see that worker's events (fine for a single-process
`uvicorn` prototype, worth knowing if this ever grows into a real deployment).
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any

_subscribers: set[asyncio.Queue] = set()
_history: deque[dict[str, Any]] = deque(maxlen=40)
_lock = asyncio.Lock()


def _serialize(event_type: str, payload: dict) -> dict:
    return {"type": event_type, "payload": dict(payload or {}), "ts": time.time()}


def sse_pack(event: dict) -> str:
    """One EventSource frame. Compact JSON so a payload cannot split the stream."""
    return f"data: {json.dumps(event, default=str, separators=(',', ':'))}\n\n"


def emit(event_type: str, payload: dict | None = None) -> None:
    """Announce a committed mutation. Never raises; the cadastre must not 500 for a UI feed."""
    publish_sync(event_type, dict(payload or {}))


async def publish(event_type: str, payload: dict) -> None:
    """Fire-and-forget an event to every currently-connected subscriber.

    Safe to call from a sync request handler via `publish_sync` below; call
    this directly from async code.
    """
    event = _serialize(event_type, payload)
    _history.append(event)
    async with _lock:
        targets = list(_subscribers)
    for queue in targets:
        # Subscribers are bounded queues (see `subscribe`); a slow/gone
        # client should never block or crash a publish for everyone else.
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


def publish_sync(event_type: str, payload: dict) -> None:
    """Call `publish` from a regular (non-async) request handler.

    FastAPI runs sync `def` endpoints in a thread pool, so there is no
    running event loop to schedule onto directly; this hands the coroutine
    to the loop this module was imported into (the app's main loop) via
    `run_coroutine_threadsafe`, and never raises if there's nobody listening
    yet or the loop isn't reachable — a demo action should never 500 just
    because the live feed had a hiccup.
    """
    try:
        loop = _get_loop()
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(publish(event_type, payload), loop)
    except Exception:
        pass


_main_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop | None:
    return _main_loop


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once at app startup so `publish_sync` (used from sync request
    handlers running in FastAPI's thread pool) can reach the main loop."""
    global _main_loop
    _main_loop = loop


async def subscribe():
    """Async generator yielding events as they're published, starting with
    a short backlog so a tab that just opened the live feed isn't staring
    at an empty list."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _lock:
        _subscribers.add(queue)
    try:
        for event in list(_history)[-10:]:
            yield event
        while True:
            event = await queue.get()
            yield event
    finally:
        async with _lock:
            _subscribers.discard(queue)

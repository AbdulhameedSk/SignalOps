"""
broker.py — in-process pub/sub for live event streaming.

When the agent does anything, workers call publish(). Each incident has a
list of subscriber queues; the SSE endpoint in app.py creates a queue,
subscribes, and forwards everything to the browser.

Honest limitation (worth knowing for interviews): this works on ONE process.
Multi-replica deploys need a real broker — Redis pub/sub or Postgres
LISTEN/NOTIFY. The interface (publish/subscribe) wouldn't change.
"""
import asyncio
from collections import defaultdict

_subs: dict[int, set[asyncio.Queue]] = defaultdict(set)


def publish(incident_id: int, event: dict):
    for q in list(_subs[incident_id]):
        q.put_nowait(event)


def subscribe(incident_id: int) -> asyncio.Queue:
    q = asyncio.Queue()
    _subs[incident_id].add(q)
    return q


def unsubscribe(incident_id: int, q: asyncio.Queue):
    _subs[incident_id].discard(q)

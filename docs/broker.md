# broker.py — live event streaming

## What it does

In-process pub/sub: when the agent emits an event, `publish()` pushes it to
every subscriber's `asyncio.Queue`. The SSE endpoint subscribes, and the
browser sees the investigation live.

## The honest limitation

`_subs` is a Python dict — it only works **inside one process**. Run two
replicas and a subscriber on replica A misses events published on replica B.

**Upgrade path:** Redis pub/sub or Postgres `LISTEN/NOTIFY`. The interface
(`publish`/`subscribe`/`unsubscribe`) is designed to be swapped — callers
never touch the internals.

## Why not just poll?

You could poll `GET /api/incidents/{id}/events?after_id=N` every 2s — it
works, but SSE gives sub-second updates and one open connection instead of
repeated requests. For a live ops dashboard, the difference is visible.

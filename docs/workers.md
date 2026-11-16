# workers.py — the pool that runs investigations

## The loop

`MAX_WORKERS` async tasks each run forever:

1. `queue.claim()` — get the next runnable job (or sleep 1s and retry).
2. `agent.investigate(incident_id)` — run the full agent loop.
3. `queue.complete()` or `queue.fail()` — record the outcome.

## Why `run_in_executor`?

`agent.investigate` is **blocking** (sync Anthropic client — each API call
waits). If we called it directly in the async worker, it would freeze the
event loop — SSE streams would stall, other workers couldn't claim jobs.
`run_in_executor` runs it in a thread pool so the event loop stays free.

This is the standard fix for "sync library in an async service" — worth
knowing because it comes up constantly with LLM SDKs.

## Why asyncio instead of Celery?

Celery needs Redis/RabbitMQ — an extra service to deploy and learn. Our
jobs are I/O-bound (waiting on the LLM), so asyncio concurrency is plenty.
Same pattern, less infrastructure. The docs note when to upgrade.

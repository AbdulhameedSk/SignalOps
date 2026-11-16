# tests/ — offline coverage

## What's tested

`tests/test_queue.py` — 4 tests, no API key needed, runs in seconds:

- **`test_claim_once`** — a job can only be claimed once (concurrency
  safety of `BEGIN IMMEDIATE`)
- **`test_idempotent_dedupe_not_needed_but_retry_works`** — failed jobs
  return to `queued` with a future `run_at` (backoff works)
- **`test_dead_after_max_attempts`** — 3 failures → status `dead`
- **`test_incident_and_events`** — basic create/read of incidents, events,
  actions

## What's deliberately not tested

The agent loop and the API — those need an `ANTHROPIC_API_KEY` and would
be flaky/slow in unit tests. The demo loop + `/api/health` are the smoke
test for those.

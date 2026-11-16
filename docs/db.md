# db.py — the data model

## Why one file, plain SQL

No ORM on purpose. Seven tables, each mapping to a concept you'd explain
in a system-design interview. The SQL is standard — swap the driver for
Postgres and nothing else changes.

## The tables

- **incidents** — one row per problem. `status` drives the UI:
  `new → investigating → awaiting_approval → resolved`.
- **events** — the timeline. Every agent step, tool call, and human action
  becomes an event. Two uses: replay history (SSE backfill) and audit trail.
- **actions** — proposed remediation steps. `pending` until a human decides.
  This is the persistence layer for human-in-the-loop.
- **jobs** — the work queue. `status`, `attempts`, `run_at` (backoff).
  Claimed by workers, not the API.
- **logs / runbooks / metrics** — seeded dummy data. In production these
  tables wouldn't exist — the agent's read tools would call your real
  observability stack instead.

## Key details

- `PRAGMA journal_mode=WAL` — lets readers and writers coexist; SSE readers
  don't block the worker writing events.
- `conn.row_factory = sqlite3.Row` — rows become dicts, so `row["status"]`
  instead of `row[2]`.
- `seed_insert` whitelists table→columns explicitly — never string-format
  untrusted table/column names into SQL.

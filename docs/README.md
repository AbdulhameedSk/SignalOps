# SignalOps docs — how every file works

Read in this order; each file builds on the last.

| Doc | File | You'll understand |
| --- | ---- | ----------------- |
| 1 | [Data model](db.md) | `db.py` — the 7 tables and why each exists |
| 2 | [The queue](queue.md) | `jobs.py` — claim semantics, backoff, dead-lettering |
| 3 | [The event broker](broker.md) | `broker.py` — in-process pub/sub for SSE |
| 4 | [The agent's tools](tools.md) | `tools.py` — read/write split, human-in-the-loop design |
| 5 | [The investigator](agent.md) | `agent.py` — the loop, event emission, signal interception |
| 6 | [Dummy data](seed.md) | `seed.py` — scenarios, runbooks, why seeding works |
| 7 | [Worker pool](workers.md) | `workers.py` — async workers, thread offloading |
| 8 | [The API](app.md) | `app.py` — endpoints, SSE endpoint internals |
| 9 | [The dashboard](frontend.md) | `static/` — fetch + EventSource, no build step |
| 10 | [Tests](tests.md) | `tests/` — what's covered offline |

## Upgrade paths worth knowing

- **SQLite → Postgres**: same SQL, swap the driver (`psycopg`), `BEGIN
  IMMEDIATE` becomes `SELECT ... FOR UPDATE SKIP LOCKED`.
- **In-process broker → Redis**: swap `broker.py` for Redis pub/sub when
  running multiple replicas.
- **Seeded data → real monitoring**: replace the three read tools in
  `tools.py` with API calls to Datadog/Loki/CloudWatch.
- **Simulated actions → real execution**: `/api/actions/{id}/decide` is
  where you'd call `kubectl rollout`, feature-flag APIs, or ticket systems.

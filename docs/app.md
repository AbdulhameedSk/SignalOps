# app.py — the API and the door to the outside world

## Endpoints

- `GET /` — serves the dashboard
- `GET /api/incidents` — incident list (sidebar)
- `POST /api/demo` — spawn a seeded incident + enqueue investigation
- `POST /api/incidents/{id}/investigate` — re-run investigation
- `GET /api/incidents/{id}/events` — full timeline (used for replay)
- `GET /api/incidents/{id}/stream` — **SSE**: replay + live tail
- `GET /api/incidents/{id}/actions` — pending actions for approval UI
- `POST /api/actions/{id}/decide` — **the human-in-the-loop endpoint**
- `POST /api/alerts` — **the real-world door**: external systems post here
- `GET /api/stats` — queue depth + counts
- `GET /api/health`

## The SSE endpoint (the interesting one)

`/stream` does two things: replays every existing event from the DB (so a
page refresh doesn't lose history), then subscribes to the broker for live
ones. `finally: broker.unsubscribe` cleans up on disconnect — no leak.

## The human approval endpoint

`POST /api/actions/{id}/decide` with `{decision: approved|rejected}`.
On approve: `status=executed` + a timeline event saying "(simulated)" —
in production this is where you'd call the real remediation API. On reject:
`status=rejected`. If no pending actions remain → incident resolves.

## `/api/alerts` — real-world integration

Accepts `{title, service, severity, description}`. Grafana contact points
and PagerDuty webhooks can be configured to POST this shape — one endpoint,
two alerting systems.

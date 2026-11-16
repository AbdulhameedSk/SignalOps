# seed.py — dummy data that looks real

## Why seeding works for a demo

You can't cause a real outage to demo this. So we plant three realistic
failure scenarios — complete with logs, metrics, and runbooks — and let
the agent investigate them exactly as it would real data.

The agent **can't tell the difference**: it calls `get_logs("checkout-api")`
and gets back `TimeoutError` entries with realistic timestamps. That's the
point — same tool interface, same investigation flow.

## The scenarios

- **`db_timeout`** — checkout API: pool exhaustion → timeouts → 500s.
  Metrics: error_rate spikes to 42%, latency hits 5s.
- **`memory_leak`** — user-svc: monotonic heap growth → GC thrash → OOM
  restart.
- **`deploy_regression`** — search-svc: post-deploy latency, cache hit
  ratio collapse. The "was it the deploy?" mystery every SRE knows.

## The runbooks

Three realistic runbooks matching the scenarios. When the agent calls
`get_runbook("db_timeouts")`, it gets actual troubleshooting guidance —
which is how it grounds its `propose_action` suggestions.

## `spawn_demo_incident()`

Picks a random scenario, creates a live incident row, returns it. The
**+ Simulate incident** button calls this.

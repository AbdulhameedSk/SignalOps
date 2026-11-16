# tools.py — what the agent can do

## The split that matters

**Read tools** (safe, unrestricted):
- `get_logs(service)` — recent log lines
- `get_runbook(topic)` — troubleshooting doc
- `get_metrics(service, metric)` — time series

**Write tools** (each deliberately constrained):
- `add_timeline_event` — appends to the timeline (safe to let loose)
- `propose_action` — creates a *pending* action; a human must approve
- `conclude` — writes the final summary; call exactly once, last

Notice what's **missing**: no `restart_service`, no `run_command`. The agent
can't touch anything real. That's the human-in-the-loop contract — and
it's a design decision, not a limitation.

## The closure trick

`build_tools(incident_id)` returns the schemas and dispatch bound to one
incident. The model never supplies an incident id — it can't accidentally
write to the wrong incident. Same pattern as Sentinel's `submit_review`.

## The signal prefix pattern

Write tools return strings like `TIMELINE:...`, `ACTION_CREATED:...`,
`CONCLUDE:...`. `agent.py` intercepts these and performs the side effect
(updating the incident, creating an action). The tool function itself
stays pure — easy to test, easy to reason about.

## Connecting real data

Replace the three read functions with calls to Datadog/Loki/wiki APIs.
Schemas stay the same — the agent doesn't know or care where data lives.

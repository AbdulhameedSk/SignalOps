# agent.py — the investigator

## The loop (familiar by now)

Same shape as your other agents: `messages` + tool schemas → Claude →
execute tool calls → feed results back → repeat until `end_turn` or
`MAX_STEPS`.

## What's new

**1. Every step is an event.** `_emit()` writes to the `events` table
(durable, replayable) AND publishes to live subscribers (the SSE feed).
One call, both durability and liveness.

**2. Signal interception.** When a tool result starts with `TIMELINE:`,
`ACTION_CREATED:`, or `CONCLUDE:`, this file performs the side effect:
- `CONCLUDE:` → parses `root_cause` + `summary` → updates the incident row
- `TIMELINE:` → emits a timeline event
- The loop continues; the model just sees a normal tool result.

**3. Status reconciliation.** After the loop: pending actions →
`awaiting_approval` (a human must decide); none → `resolved`.

## The prompt's job

`INVESTIGATOR_PROMPT` gives a workflow: logs first, then metrics, then
runbook, then act. And the key safety line: *"never claim an action was
executed"* — the agent proposes, humans dispose.

## `max_steps = 20`

An investigator that can't reach a conclusion in 20 tool calls is either
stuck or the incident is too complex — either way, cap it and let a human
look at the partial timeline.

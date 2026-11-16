"""
tools.py — what the investigator agent can DO.

Read tools query the seeded dummy data (logs, runbooks, metrics). In a real
deployment these same tool signatures would call Datadog/CloudWatch/wiki
APIs instead — the agent loop doesn't care where data comes from.

Write tools are deliberately constrained:
  - add_timeline_event  : appends to the incident timeline (safe)
  - propose_action      : creates a PENDING action — a human must approve
  - conclude            : writes the final incident summary (safe)

Notice what's missing: no "restart_service" or "run_command". The agent
proposes; humans dispose. That's the whole human-in-the-loop pattern.
"""
import time

import db


def build_tools(incident_id: int):
    """Tool schemas + dispatch, bound to one incident via closure.

    Same trick as Sentinel's submit_review: the tools know which incident
    they're working on, so the model never supplies an incident id.
    """

    # ----- read tools -----
    def get_logs(service: str) -> str:
        rows = db.recent_logs(service)
        if not rows:
            return f"No logs found for service '{service}'."
        return "\n".join(
            f"[{time.strftime('%H:%M:%S', time.localtime(r['ts']))}] "
            f"{r['level']} {r['message']}" for r in rows)

    def get_runbook(topic: str) -> str:
        content = db.get_runbook(topic)
        if content is None:
            topics = ", ".join(db.list_runbook_topics())
            return f"No runbook '{topic}'. Available: {topics}"
        return content

    def get_metrics(service: str, metric: str) -> str:
        rows = db.metric_series(service, metric)
        if not rows:
            return f"No metric '{metric}' for service '{service}'. "
            "Try: error_rate, latency_ms, memory_mb, cpu_pct."
        return "\n".join(
            f"{time.strftime('%H:%M:%S', time.localtime(r['ts']))}: "
            f"{r['value']}" for r in rows)

    # ----- write tools -----
    def add_timeline_event(text: str) -> str:
        return f"TIMELINE:{text}"   # dispatched to db by agent.py

    def propose_action(title: str, description: str, evidence: str) -> str:
        action_id = db.create_action(incident_id, title, description, evidence)
        return f"ACTION_CREATED:{action_id}"

    def conclude(summary: str, root_cause: str) -> str:
        return f"CONCLUDE:{root_cause}\n{summary}"

    schemas = [
        {"name": "get_logs",
         "description": "Get recent log lines for a service.",
         "input_schema": {"type": "object", "properties": {
             "service": {"type": "string"}}, "required": ["service"]}},
        {"name": "get_runbook",
         "description": "Read a troubleshooting runbook by topic. Call with an empty string to list topics first.",
         "input_schema": {"type": "object", "properties": {
             "topic": {"type": "string"}}, "required": ["topic"]}},
        {"name": "get_metrics",
         "description": "Get a metric time series for a service (error_rate, latency_ms, memory_mb, cpu_pct).",
         "input_schema": {"type": "object", "properties": {
             "service": {"type": "string"},
             "metric": {"type": "string"}}, "required": ["service", "metric"]}},
        {"name": "add_timeline_event",
         "description": "Record a finding on the incident timeline for the humans watching.",
         "input_schema": {"type": "object", "properties": {
             "text": {"type": "string"}}, "required": ["text"]}},
        {"name": "propose_action",
         "description": "Propose a remediation action. It goes to a human for approval — never assume it runs automatically.",
         "input_schema": {"type": "object", "properties": {
             "title": {"type": "string"},
             "description": {"type": "string"},
             "evidence": {"type": "string"}},
             "required": ["title", "description", "evidence"]}},
        {"name": "conclude",
         "description": "Finish the investigation: state the root cause and a summary. Call LAST, exactly once.",
         "input_schema": {"type": "object", "properties": {
             "summary": {"type": "string"},
             "root_cause": {"type": "string"}},
             "required": ["summary", "root_cause"]}},
    ]

    fns = {"get_logs": get_logs, "get_runbook": get_runbook,
           "get_metrics": get_metrics,
           "add_timeline_event": add_timeline_event,
           "propose_action": propose_action, "conclude": conclude}

    def dispatch(name, inputs):
        fn = fns.get(name)
        return fn(**inputs) if fn else f"ERROR: unknown tool {name}"

    return schemas, dispatch

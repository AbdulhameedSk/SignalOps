"""
agent.py — the incident investigator.

Same agent loop you've now built twice (send messages + tool schemas,
execute tool calls, feed results back until the model stops). The new part
is what surrounds it: every step is written to the events table AND pushed
to live subscribers, so the dashboard can show the investigation happening
in real time.

Special tool-result handling lives here rather than in tools.py: results
prefixed with TIMELINE:/ACTION_CREATED:/CONCLUDE: are signals for this
file to update the incident, not just text for the model.
"""
import os

import anthropic
from dotenv import load_dotenv

import broker
import db
from tools import build_tools

load_dotenv()

MODEL = os.getenv("MODEL", "claude-sonnet-4-5")
MAX_STEPS = 20

INVESTIGATOR_PROMPT = """You are an SRE incident investigator for SignalOps.
A service has an incident. Your job:

1. get_logs for the affected service — look for the first anomalous entries.
2. get_metrics for error_rate/latency_ms/memory_mb/cpu_pct — confirm impact.
3. get_runbook for relevant troubleshooting guidance (list topics first if unsure).
4. add_timeline_event for each significant finding — humans are watching live.
5. propose_action for remediation steps. You propose, humans decide — never
   claim an action was executed.
6. conclude LAST with root cause and summary.

Be concrete: cite log lines and metric values as evidence. If evidence is
thin, say so rather than guessing."""


def _emit(incident_id, kind, content):
    """Every event goes to the DB (durable timeline) AND live subscribers."""
    ev = db.add_event(incident_id, kind, content)
    broker.publish(incident_id, ev)


def investigate(incident_id: int):
    """Run the full investigation for one incident."""
    incident = db.get_incident(incident_id)
    if not incident:
        raise ValueError(f"incident {incident_id} not found")

    db.update_incident(incident_id, status="investigating")
    _emit(incident_id, "stage", "investigation started")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    schemas, dispatch = build_tools(incident_id)
    messages = [{"role": "user", "content":
                 f"Investigate incident #{incident_id}: "
                 f"'{incident['title']}' on service '{incident['service']}' "
                 f"(severity {incident['severity']})."}]

    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=MODEL, max_tokens=2048,
                                      system=INVESTIGATOR_PROMPT,
                                      tools=schemas, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})

        tool_results, done = [], False
        for block in resp.content:
            if block.type == "text":
                _emit(incident_id, "text", block.text)
            elif block.type == "tool_use":
                _emit(incident_id, "tool_call",
                      f"{block.name}({block.input})")
                result = dispatch(block.name, block.input)
                _emit(incident_id, "tool_result", result[:500])

                # Intercept the signal-prefixed results.
                if result.startswith("TIMELINE:"):
                    _emit(incident_id, "action", result[9:])
                elif result.startswith("CONCLUDE:"):
                    root_cause, _, summary = result[9:].partition("\n")
                    db.update_incident(
                        incident_id, status="awaiting_approval",
                        summary=f"[{root_cause}] {summary}")
                    done = True
                tool_results.append({"type": "tool_result",
                                     "tool_use_id": block.id,
                                     "content": result})

        if done or resp.stop_reason == "end_turn" or not tool_results:
            break
        messages.append({"role": "user", "content": tool_results})

    # Reconcile status: pending actions -> a human must approve before we
    # call it resolved. No pending actions -> investigation resolved itself.
    inc = db.get_incident(incident_id)
    pending = [a for a in db.get_actions(incident_id)
               if a["status"] == "pending"]
    if pending:
        db.update_incident(incident_id, status="awaiting_approval")
    elif inc["status"] != "resolved":
        db.update_incident(incident_id, status="resolved")
    _emit(incident_id, "stage", "investigation complete")

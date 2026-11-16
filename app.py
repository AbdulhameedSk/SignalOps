"""
app.py — the API and the door to the outside world.

    uvicorn app:app --port 8000

Endpoints:
  GET  /                          — the dashboard (static/index.html)
  GET  /api/incidents             — incident list
  POST /api/demo                  — spawn a seeded demo incident + investigate
  POST /api/incidents/{id}/investigate — re-run investigation
  GET  /api/incidents/{id}/events — full event timeline
  GET  /api/incidents/{id}/stream — SSE live event feed
  GET  /api/incidents/{id}/actions— proposed actions + status
  POST /api/actions/{id}/decide   — {decision: approved|rejected}
  POST /api/alerts                — REAL-WORLD door: external alerting
                                    (Grafana/PagerDuty-style JSON) creates an
                                    incident and queues an investigation
  GET  /api/stats                 — queue + incident counts
  GET  /api/health
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import broker
import db
import jobs as q
import seed
import workers


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    seed.seed()                        # idempotent dummy data
    workers_task = asyncio.create_task(workers.run_pool())
    yield
    workers_task.cancel()


app = FastAPI(title="SignalOps", lifespan=lifespan)
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# ---------- dashboard ----------

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


# ---------- incidents ----------

@app.get("/api/incidents")
def incidents():
    return db.list_incidents()


@app.post("/api/demo")
def demo():
    """Create a random seeded incident and queue its investigation."""
    info = seed.spawn_demo_incident()
    q.enqueue(info["id"])
    return info


@app.post("/api/incidents/{incident_id}/investigate")
def investigate(incident_id: int):
    if not db.get_incident(incident_id):
        raise HTTPException(404, "incident not found")
    job_id = q.enqueue(incident_id)
    return {"job_id": job_id}


@app.get("/api/incidents/{incident_id}/events")
def events(incident_id: int):
    return db.get_events(incident_id)


@app.get("/api/incidents/{incident_id}/stream")
async def stream(incident_id: int):
    """SSE: replay existing events, then push live ones as they happen."""
    sub = broker.subscribe(incident_id)

    async def gen():
        try:
            for ev in db.get_events(incident_id):
                yield f"data: {json.dumps(ev)}\n\n"
            while True:
                ev = await sub.get()
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            broker.unsubscribe(incident_id, sub)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- actions (human approval) ----------

@app.get("/api/incidents/{incident_id}/actions")
def actions(incident_id: int):
    return db.get_actions(incident_id)


class Decision(BaseModel):
    decision: str  # "approved" | "rejected"


@app.post("/api/actions/{action_id}/decide")
def decide(action_id: int, body: Decision):
    incident_id = _action_incident(action_id)
    if body.decision == "approved":
        # SIMULATED execution. In production this is where you'd call the
        # real remediation API (kubectl, feature flags, ticket system).
        db.set_action_status(action_id, "executed")
        ev = db.add_event(incident_id, "human",
                          f"Action #{action_id} approved and executed (simulated)")
        broker.publish(incident_id, ev)
    else:
        db.set_action_status(action_id, "rejected")
        ev = db.add_event(incident_id, "human",
                          f"Action #{action_id} rejected")
        broker.publish(incident_id, ev)

    # resolve the incident when no pending actions remain
    pending = [a for a in db.get_actions(incident_id)
               if a["status"] == "pending"]
    if not pending:
        db.update_incident(incident_id, status="resolved")
        ev = db.add_event(incident_id, "stage", "incident resolved")
        broker.publish(incident_id, ev)
    return {"status": body.decision}


def _action_incident(action_id: int) -> int:
    with db._conn() as conn:
        row = conn.execute("SELECT incident_id FROM actions WHERE id=?",
                           (action_id,)).fetchone()
    if not row:
        raise HTTPException(404, "action not found")
    return row["incident_id"]


# ---------- real-world ingestion ----------

class Alert(BaseModel):
    """Generic alert shape — map Grafana/PagerDuty payloads to this."""
    title: str
    service: str
    severity: str = "high"
    description: str = ""


@app.post("/api/alerts")
def alerts(alert: Alert):
    """External alerting systems POST here. Creates incident + job."""
    iid = db.create_incident(alert.title, alert.service, alert.severity,
                             source="webhook")
    if alert.description:
        db.add_event(iid, "human", f"Alert detail: {alert.description}")
    q.enqueue(iid)
    return {"incident_id": iid, "status": "queued"}


# ---------- ops ----------

@app.get("/api/stats")
def stats():
    return {"queue": q.stats(),
            "incidents": len(db.list_incidents(500))}


@app.get("/api/health")
def health():
    return {"status": "ok"}

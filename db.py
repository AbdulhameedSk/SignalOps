"""
db.py — the database layer. One SQLite file, plain SQL, no ORM.

SQLite is deliberate: zero config, works on free deploy tiers, and the SQL
is standard — swapping to Postgres later is a driver change, not a rewrite
(the schema and queries stay the same).

Tables and why they exist:
  incidents — the thing a human is watching (one row per problem)
  events    — the timeline: every agent step, tool call, and human action
  actions   — proposed remediation steps awaiting human approval
  jobs      — the work queue: "someone needs to investigate incident X"
  logs      — dummy service logs the agent can query (seeded)
  runbooks  — troubleshooting docs the agent can read (seeded)
  metrics   — dummy metric points the agent can check (seeded)
"""
import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "signalops.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    service TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',   -- new|investigating|awaiting_approval|resolved
    summary TEXT,
    source TEXT DEFAULT 'demo',           -- demo | webhook
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    kind TEXT NOT NULL,                   -- stage|text|tool_call|tool_result|action|human
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|executed
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',   -- queued|claimed|done|failed|dead
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    run_at REAL NOT NULL,                 -- backoff: earliest claim time
    error TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runbooks (
    topic TEXT PRIMARY KEY,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    ts REAL NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row      # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")  # readers don't block writers
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript(SCHEMA)


# ---------- incidents ----------

def create_incident(title, service, severity, source="demo") -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO incidents (title, service, severity, source, created_at)"
            " VALUES (?,?,?,?,?)",
            (title, service, severity, source, time.time()))
        return cur.lastrowid


def list_incidents(limit=50) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,))]


def get_incident(incident_id) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id=?",
                           (incident_id,)).fetchone()
    return dict(row) if row else None


def update_incident(incident_id, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as conn:
        conn.execute(f"UPDATE incidents SET {sets} WHERE id=?",
                     (*fields.values(), incident_id))


# ---------- events (the timeline) ----------

def add_event(incident_id, kind, content) -> dict:
    if not isinstance(content, str):
        content = json.dumps(content)
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (incident_id, kind, content, created_at)"
            " VALUES (?,?,?,?)",
            (incident_id, kind, content, time.time()))
        return {"id": cur.lastrowid, "incident_id": incident_id,
                "kind": kind, "content": content}


def get_events(incident_id, after_id=0) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM events WHERE incident_id=? AND id>? ORDER BY id",
            (incident_id, after_id))]


# ---------- actions (human-in-the-loop) ----------

def create_action(incident_id, title, description, evidence="") -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO actions (incident_id, title, description, evidence,"
            " created_at) VALUES (?,?,?,?,?)",
            (incident_id, title, description, evidence, time.time()))
        return cur.lastrowid


def get_actions(incident_id) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM actions WHERE incident_id=? ORDER BY id",
            (incident_id,))]


def set_action_status(action_id, status):
    with _conn() as conn:
        conn.execute("UPDATE actions SET status=? WHERE id=?",
                     (status, action_id))


# ---------- seeded data reads (used by agent tools) ----------

def recent_logs(service, limit=30) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT level, message, ts FROM logs WHERE service=?"
            " ORDER BY ts DESC LIMIT ?", (service, limit))]


def get_runbook(topic) -> str | None:
    with _conn() as conn:
        row = conn.execute("SELECT content FROM runbooks WHERE topic=?",
                           (topic,)).fetchone()
    return row["content"] if row else None


def list_runbook_topics() -> list[str]:
    with _conn() as conn:
        return [r["topic"] for r in conn.execute(
            "SELECT topic FROM runbooks")]


def metric_series(service, metric, limit=20) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT value, ts FROM metrics WHERE service=? AND metric=?"
            " ORDER BY ts LIMIT ?", (service, metric, limit))]


def seed_insert(table, rows: list[tuple]):
    cols = {  # table -> column list, kept explicit so nothing is guessed
        "logs": "service, level, message, ts",
        "runbooks": "topic, content",
        "metrics": "service, metric, value, ts",
    }[table]
    marks = ",".join("?" for _ in cols.split(","))
    with _conn() as conn:
        conn.executemany(f"INSERT OR REPLACE INTO {table} ({cols})"
                         f" VALUES ({marks})", rows)

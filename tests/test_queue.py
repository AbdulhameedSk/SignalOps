"""Offline tests — no API key needed. Run: pytest tests/ -v"""
import os
import sys
import tempfile

# point the DB at a temp file BEFORE importing app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.mkdtemp()
import db
db.DB_PATH = os.path.join(_tmp, "test.db")
import jobs as q

db.init_db()


def test_claim_once():
    iid = db.create_incident("t", "svc", "high")
    jid = q.enqueue(iid)
    job = q.claim()
    assert job["id"] == jid
    assert q.claim() is None          # nothing left to claim


def test_idempotent_dedupe_not_needed_but_retry_works():
    iid = db.create_incident("t2", "svc", "high")
    jid = q.enqueue(iid)
    job = q.claim()
    q.fail(job["id"], "boom")
    # failed job goes back to queued with a future run_at (backoff)
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    assert row["status"] == "queued"
    assert row["run_at"] > row["created_at"]


def test_dead_after_max_attempts():
    iid = db.create_incident("t3", "svc", "high")
    jid = q.enqueue(iid)
    for _ in range(3):
        job = q.claim()
        if job is None:
            # backoff delay — force run_at into the past for the test
            with db._conn() as conn:
                conn.execute("UPDATE jobs SET run_at=0 WHERE id=?", (jid,))
            job = q.claim()
        q.fail(job["id"], "boom")
    with db._conn() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()
    assert row["status"] == "dead"


def test_incident_and_events():
    iid = db.create_incident("db on fire", "db", "critical")
    db.add_event(iid, "stage", "investigation started")
    db.create_action(iid, "Restart", "restart the db", "evidence")
    inc = db.get_incident(iid)
    assert inc["status"] == "new"
    assert len(db.get_events(iid)) == 1
    assert db.get_actions(iid)[0]["status"] == "pending"

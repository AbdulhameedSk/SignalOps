"""
jobs.py — a database-backed job queue.

Why a queue at all? Because "the API endpoint called the LLM directly" breaks
the moment two incidents arrive at once, or a request times out mid-agent-loop.
The queue decouples *accepting* work from *doing* work:

    API enqueues a job -> returns instantly
    worker claims job -> runs investigation -> marks done/failed
    failure -> retry with exponential backoff -> 'dead' after max_attempts

SQLite's BEGIN IMMEDIATE makes claim() atomic — two workers can't grab the
same job. On Postgres you'd use SELECT ... FOR UPDATE SKIP LOCKED (the
standard production pattern); the SQL shape is the same.
"""
import time
import db

BACKOFF_BASE = 2  # seconds: retry delays are 2s, 4s, 8s...


def enqueue(incident_id) -> int:
    with db._conn() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (incident_id, run_at, created_at) VALUES (?,?,?)",
            (incident_id, time.time(), time.time()))
        return cur.lastrowid


def claim() -> dict | None:
    """Atomically claim the next runnable job. None if queue is empty."""
    now = time.time()
    with db._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' AND run_at<=?"
            " ORDER BY created_at LIMIT 1", (now,)).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE jobs SET status='claimed', attempts=attempts+1 WHERE id=?",
            (row["id"],))
        conn.execute("COMMIT")
    return dict(row)


def complete(job_id):
    with db._conn() as conn:
        conn.execute("UPDATE jobs SET status='done' WHERE id=?", (job_id,))


def fail(job_id, error: str):
    """Retry with backoff, or mark dead after max_attempts."""
    with db._conn() as conn:
        row = conn.execute("SELECT attempts, max_attempts FROM jobs WHERE id=?",
                           (job_id,)).fetchone()
        if row["attempts"] >= row["max_attempts"]:
            conn.execute("UPDATE jobs SET status='dead', error=? WHERE id=?",
                         (error, job_id))
        else:
            delay = BACKOFF_BASE ** row["attempts"]
            conn.execute(
                "UPDATE jobs SET status='queued', run_at=?, error=? WHERE id=?",
                (time.time() + delay, error, job_id))


def stats() -> dict:
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) c FROM jobs GROUP BY status").fetchall()
    return {r["status"]: r["c"] for r in rows}

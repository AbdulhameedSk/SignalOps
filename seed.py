"""
seed.py — dummy data so the demo works with zero real infrastructure.

This is how you demonstrate SignalOps without a real outage: we plant three
realistic failure scenarios (logs + metrics + runbooks) in the database.
The agent investigates them exactly as it would real data — it can't tell
the difference, which is the point.

Connecting real systems later = replace these tables with tools that call
your log/metric/runbook APIs. Tool signatures stay the same.
"""
import random
import time

import db


def _series(service, metric, values, step_s=30):
    """Build a metric time series ending ~now."""
    now = time.time()
    return [(service, metric, v, now - (len(values) - i) * step_s)
            for i, v in enumerate(values)]


SCENARIOS = {
    "db_timeout": {
        "title": "Checkout API error spike",
        "service": "checkout-api",
        "severity": "critical",
        "logs": [
            ("INFO", "request completed path=/pay status=200 ms=45"),
            ("INFO", "request completed path=/pay status=200 ms=52"),
            ("WARN", "db connection pool usage 85%"),
            ("WARN", "db connection pool usage 97%"),
            ("ERROR", "TimeoutError: connection checkout-db:5432 timed out after 5000ms"),
            ("ERROR", "request failed path=/pay status=500 ms=5012"),
            ("ERROR", "db connection pool exhausted, queued 34 connections"),
            ("ERROR", "request failed path=/pay status=500 ms=5001"),
            ("ERROR", "request failed path=/cart status=500 ms=5008"),
            ("CRITICAL", "error_rate exceeded threshold: 42%"),
        ],
        "metrics": {
            "error_rate": [1, 1, 2, 5, 12, 28, 41, 43, 44, 42],
            "latency_ms": [48, 50, 62, 140, 900, 3800, 5000, 5100, 5000, 5050],
            "cpu_pct": [22, 24, 23, 25, 31, 38, 41, 40, 39, 40],
            "memory_mb": [512, 515, 518, 520, 540, 560, 575, 580, 582, 585],
        },
        "runbook_topic": "db_timeouts",
    },
    "memory_leak": {
        "title": "User service memory climbing",
        "service": "user-svc",
        "severity": "high",
        "logs": [
            ("INFO", "heap snapshot ok, 480MB"),
            ("INFO", "gc pause 120ms"),
            ("WARN", "gc pause 890ms"),
            ("WARN", "heap usage 78%"),
            ("WARN", "gc pause 2100ms, old-gen 91%"),
            ("ERROR", "heap usage 96%, allocation stalls"),
            ("ERROR", "OutOfMemoryError: Java heap space"),
            ("CRITICAL", "container restarted by orchestrator"),
        ],
        "metrics": {
            "error_rate": [0, 0, 1, 2, 3, 8, 15, 22],
            "memory_mb": [480, 495, 530, 590, 680, 790, 920, 1024],
            "latency_ms": [30, 32, 45, 80, 160, 400, 900, 1400],
            "cpu_pct": [15, 16, 30, 55, 72, 85, 90, 45],
        },
        "runbook_topic": "memory_leaks",
    },
    "deploy_regression": {
        "title": "Search latency after deploy v2.14",
        "service": "search-svc",
        "severity": "medium",
        "logs": [
            ("INFO", "deploy v2.13 completed"),
            ("INFO", "deploy v2.14 started, 3 replicas"),
            ("INFO", "deploy v2.14 completed"),
            ("WARN", "p95 latency 450ms (baseline 120ms)"),
            ("WARN", "cache hit ratio dropped to 31% (baseline 88%)"),
            ("ERROR", "query timeout path=/search?q=shoes"),
            ("WARN", "new index warming detected on all replicas"),
            ("ERROR", "query timeout path=/search?q=jacket"),
        ],
        "metrics": {
            "error_rate": [0, 0, 1, 4, 6, 7, 6, 6],
            "latency_ms": [118, 121, 145, 310, 450, 470, 460, 455],
            "cpu_pct": [30, 32, 60, 78, 82, 80, 79, 78],
            "memory_mb": [700, 705, 780, 840, 860, 870, 865, 868],
        },
        "runbook_topic": "deploy_regressions",
    },
}

RUNBOOKS = {
    "db_timeouts": """DB TIMEOUT RUNBOOK
1. Check connection pool exhaustion — most common cause.
2. If pool exhausted: check for long-running queries or a leaked transaction.
3. Safe actions: restart one replica to drain stuck connections; scale pool;
   kill the blocking query.
4. NEVER restart all replicas at once during an incident.""",
    "memory_leaks": """MEMORY LEAK RUNBOOK
1. Confirm monotonic heap growth across GC cycles (metrics memory_mb).
2. Check recent deploys — most leaks ship in new code.
3. Safe action: rolling restart buys time; capture a heap dump FIRST for
   later analysis.
4. Long-term: profile allocations, look for unbounded caches or listeners.""",
    "deploy_regressions": """DEPLOY REGRESSION RUNBOOK
1. Correlate symptom start time with deploy events — if it started right
   after a deploy, suspect the deploy.
2. Check cache hit ratios and index warming — cold caches cause latency
   spikes that look like outages.
3. Safe action: rollback to previous version if metrics don't recover in
   ~15 min; document rollback reasoning.
4. After rollback: file a regression ticket with the diff.""",
}


def seed():
    """Populate logs/metrics/runbooks if they're not already there."""
    db.init_db()
    db.seed_insert("runbooks", list(RUNBOOKS.items()))

    now = time.time()
    log_rows, metric_rows = [], []
    for name, sc in SCENARIOS.items():
        for i, (level, msg) in enumerate(sc["logs"]):
            log_rows.append((sc["service"], level, msg,
                             now - (len(sc["logs"]) - i) * 45))
        for metric, values in sc["metrics"].items():
            metric_rows += _series(sc["service"], metric, values)
    db.seed_insert("logs", log_rows)
    db.seed_insert("metrics", metric_rows)


def spawn_demo_incident() -> dict:
    """Pick a random scenario and create a live incident from it."""
    name = random.choice(list(SCENARIOS))
    sc = SCENARIOS[name]
    iid = db.create_incident(sc["title"], sc["service"], sc["severity"],
                             source="demo")
    return {"id": iid, "scenario": name, **{k: sc[k]
            for k in ("title", "service", "severity")}}

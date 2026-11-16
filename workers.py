"""
workers.py — the pool that actually runs investigations.

MAX_WORKERS async tasks loop forever: claim a job, run the agent, mark it
done. If the agent crashes, the job goes back to the queue with backoff
(queue.fail), and after max_attempts it lands in 'dead' for a human.

This is the same shape as Celery/SQS workers — asyncio instead of separate
processes because our work is I/O-bound (waiting on the LLM API).
"""
import asyncio
import os

import agent
import broker
import db
import jobs as q

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "3"))


async def _worker(worker_id: int):
    loop = asyncio.get_event_loop()
    while True:
        job = await loop.run_in_executor(None, q.claim)
        if job is None:
            await asyncio.sleep(1)
            continue
        iid = job["incident_id"]
        try:
            # agent.investigate is blocking (sync anthropic client) — run it
            # in a thread so other workers/SSE streams keep flowing.
            await loop.run_in_executor(None, agent.investigate, iid)
            q.complete(job["id"])
        except Exception as e:
            q.fail(job["id"], str(e))
            broker.publish(iid, {"kind": "stage",
                                 "content": f"worker {worker_id} error: {e}"})


async def run_pool():
    db.init_db()
    workers = [asyncio.create_task(_worker(i)) for i in range(MAX_WORKERS)]
    await asyncio.gather(*workers)

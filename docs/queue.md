# jobs.py — the job queue

## Why a queue at all

If the API called the LLM directly inside the HTTP request: two incidents
arriving together would fight, a slow investigation would time out the
request, and there'd be no record of work-in-progress. The queue decouples
*accepting* work from *doing* it.

## The lifecycle

```
queued -> claimed -> done
                 \-> queued (retry with backoff)
                      \-> dead (after max_attempts)
```

- **`enqueue(incident_id)`** — the API's only job: insert a row, return.
- **`claim()`** — `BEGIN IMMEDIATE` makes the SELECT+UPDATE atomic in
  SQLite. Two workers can't grab the same job. `run_at <= now` means
  backed-off jobs aren't visible yet.
- **`complete(job_id)`** — done.
- **`fail(job_id, error)`** — if attempts < max: status back to `queued`
  with `run_at = now + 2^attempts` (exponential backoff). After max
  attempts: `dead` — a human looks at it, no more automatic retries.

## The production upgrade

On Postgres this becomes `SELECT ... FOR UPDATE SKIP LOCKED` — the standard
pattern for DB-backed queues. Or swap the whole module for Celery/SQS; the
interface (`enqueue/claim/complete/fail`) stays the same.

# Background Jobs

## Purpose

The application has a durable queue in the main database for work that should
not hold an HTTP request open. Database backup creation is the first queued job.
The queue works with SQLite during development and PostgreSQL in production.

Each job records its payload, status, attempt count, lease owner, safe error
code, result and timestamps. An active deduplication key prevents two backup
jobs from being queued at the same time.

## Processing modes

Choose one normal processing mode.

### Scheduled endpoint

Call this endpoint every minute with the existing automation secret:

```bash
curl -X POST \
  -H "x-automation-secret: $AUTOMATION_CRON_SECRET" \
  https://your-domain.example/automation/cron/background-jobs
```

### Dedicated worker

Run a separate process when the hosting plan supports workers:

```bash
python3 scripts/run_background_worker.py --watch --poll-seconds 5
```

One batch can be run for deployment checks or local operations:

```bash
python3 scripts/run_background_worker.py --max-jobs 10
```

## Reliability rules

- A transaction and database lock serialize claims, while separate workers can
  process already claimed jobs concurrently.
- Retry delays follow 1, 2, 4 minutes and continue up to 60 minutes while
  attempts remain under `BACKGROUND_JOB_MAX_ATTEMPTS`.
- A running job whose lease exceeds `BACKGROUND_JOB_STALE_MINUTES` returns to
  the queue. It becomes failed after its final allowed attempt.
- Exception messages are not stored. The queue keeps only a safe error code so
  credentials or provider responses cannot leak into diagnostics.
- Completed and failed history is removed according to the retention settings.

Handlers must be idempotent because a worker can stop after completing an
external side effect but before saving the success status. Backup filenames and
the active deduplication key make repeated backup execution safe.

## Configuration

- `BACKGROUND_JOB_BATCH_SIZE=10`
- `BACKGROUND_JOB_MAX_ATTEMPTS=3`
- `BACKGROUND_JOB_STALE_MINUTES=60`
- `BACKGROUND_JOB_WARNING_MINUTES=5`
- `BACKGROUND_JOB_SUCCESS_RETENTION_DAYS=14`
- `BACKGROUND_JOB_FAILED_RETENTION_DAYS=30`

Set the stale lease above the longest expected database backup duration.

## Operations

Superadmins can inspect the queue at:

- `/system` for the health summary;
- `/backup` for backup jobs and manual processing;
- `GET /api/platform/background-jobs` for structured status and recent jobs.

The release readiness page becomes critical when a lease is stale or a job has
failed in the last 24 hours. It warns while a retry is scheduled or when a due
job has waited longer than `BACKGROUND_JOB_WARNING_MINUTES`.

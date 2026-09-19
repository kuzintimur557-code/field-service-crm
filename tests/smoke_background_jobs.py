import asyncio
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def cron_request(token=""):
    headers = []
    if token:
        headers.append((b"x-automation-secret", token.encode("utf-8")))
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/automation/cron/background-jobs",
        "headers": headers,
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    })


def main():
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        {
            "DATA_DIR": temp_dir,
            "SECRET_KEY": "background-job-smoke-secret",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
            "BACKGROUND_JOB_MAX_ATTEMPTS": "2",
            "BACKGROUND_JOB_STALE_MINUTES": "5",
            "BACKGROUND_JOB_WARNING_MINUTES": "1",
            "BACKGROUND_JOB_SUCCESS_RETENTION_DAYS": "1",
            "BACKGROUND_JOB_FAILED_RETENTION_DAYS": "2",
        },
        clear=False,
    ):
        from app import database
        from app.services.background_jobs import (
            BackgroundJobExecutionError,
            claim_next_background_job,
            cleanup_background_job_history,
            enqueue_background_job,
            get_background_queue_status,
            get_recent_background_jobs,
            process_background_jobs,
            recover_stale_background_jobs,
        )

        database.init_db()
        base_now = datetime(2026, 9, 19, 10, 0, 0)

        first = enqueue_background_job(
            "test.success",
            payload={"value": 7},
            requested_by="smoke",
            dedupe_key="success-job",
            now=base_now,
        )
        duplicate = enqueue_background_job(
            "test.success",
            payload={"value": 8},
            requested_by="smoke",
            dedupe_key="success-job",
            now=base_now,
        )
        assert first["created"] is True
        assert duplicate["created"] is False
        assert duplicate["job"]["id"] == first["job"]["id"]

        completed = process_background_jobs(
            {"test.success": lambda payload, _job: {
                "answer": payload["value"] * 2,
            }},
            worker_id="smoke-success",
            limit=1,
            now=base_now,
        )
        assert completed["claimed"] == 1
        assert completed["succeeded"] == 1
        assert completed["items"][0]["result"]["answer"] == 14
        success_job = get_recent_background_jobs("test.success", 1)[0]
        assert success_job["status"] == "succeeded"
        assert success_job["result"]["answer"] == 14

        retry = enqueue_background_job(
            "test.retry",
            payload={},
            dedupe_key="retry-job",
            max_attempts=2,
            now=base_now,
        )

        def unsafe_failure(_payload, _job):
            raise RuntimeError("private-password-must-not-be-stored")

        first_failure = process_background_jobs(
            {"test.retry": unsafe_failure},
            worker_id="smoke-retry-one",
            limit=1,
            now=base_now,
        )
        assert first_failure["retried"] == 1
        retry_job = get_recent_background_jobs("test.retry", 1)[0]
        assert retry_job["id"] == retry["job"]["id"]
        assert retry_job["status"] == "pending"
        assert retry_job["attempts"] == 1
        assert retry_job["last_error"] == "unexpected_RuntimeError"
        assert "private-password" not in repr(retry_job)
        retry_status = get_background_queue_status(now=base_now)
        assert retry_status["status"] == "warning"
        assert retry_status["retry_pending"] == 1

        second_failure = process_background_jobs(
            {"test.retry": unsafe_failure},
            worker_id="smoke-retry-two",
            limit=1,
            now=base_now + timedelta(minutes=2),
        )
        assert second_failure["failed"] == 1
        retry_job = get_recent_background_jobs("test.retry", 1)[0]
        assert retry_job["status"] == "failed"
        assert retry_job["attempts"] == 2

        enqueue_background_job(
            "test.permanent",
            payload={},
            max_attempts=5,
            now=base_now,
        )

        def permanent_failure(_payload, _job):
            raise BackgroundJobExecutionError(
                "unsupported_payload",
                retryable=False,
            )

        permanent = process_background_jobs(
            {"test.permanent": permanent_failure},
            worker_id="smoke-permanent",
            limit=1,
            now=base_now,
        )
        assert permanent["failed"] == 1
        permanent_job = get_recent_background_jobs("test.permanent", 1)[0]
        assert permanent_job["attempts"] == 1
        assert permanent_job["last_error"] == "unsupported_payload"

        stale = enqueue_background_job(
            "test.stale",
            payload={},
            max_attempts=2,
            now=base_now,
        )
        claimed = claim_next_background_job("stale-worker-one", now=base_now)
        assert claimed["id"] == stale["job"]["id"]
        recovered = recover_stale_background_jobs(
            now=base_now + timedelta(minutes=6),
        )
        assert recovered == {"recovered": 1, "failed": 0}
        claimed_again = claim_next_background_job(
            "stale-worker-two",
            now=base_now + timedelta(minutes=6),
        )
        assert claimed_again["attempts"] == 2
        stale_failed = recover_stale_background_jobs(
            now=base_now + timedelta(minutes=12),
        )
        assert stale_failed == {"recovered": 0, "failed": 1}

        def enqueue_same(_index):
            return enqueue_background_job(
                "test.concurrent",
                payload={},
                dedupe_key="concurrent-dedupe",
                now=base_now,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_results = list(executor.map(enqueue_same, range(2)))
        assert sum(1 for item in concurrent_results if item["created"]) == 1

        queue_status = get_background_queue_status(
            now=base_now + timedelta(minutes=12),
        )
        assert queue_status["status"] == "critical"
        assert queue_status["failed_24h"] >= 2
        assert queue_status["stale_running"] == 0

        connection = database.connect()
        connection.execute("""
            UPDATE background_jobs
            SET finished_at='2026-09-01 00:00:00'
            WHERE status IN ('succeeded', 'failed')
        """)
        connection.commit()
        connection.close()
        assert cleanup_background_job_history(
            now=base_now,
        ) >= 3

        try:
            enqueue_background_job("../unsafe", payload={})
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe background job type accepted")

        from app import main as crm

        connection = database.connect()
        connection.execute("DELETE FROM background_jobs")
        connection.commit()
        connection.close()

        with patch.object(crm, "get_user", return_value="super"), patch.object(
            crm,
            "get_role",
            return_value="superadmin",
        ):
            queued_response = asyncio.run(
                crm.backup_create(SimpleNamespace())
            )
            assert queued_response.status_code == 302
            assert "notice=backup_queued" in queued_response.headers["location"]
            duplicate_response = asyncio.run(
                crm.backup_create(SimpleNamespace())
            )
            assert "notice=backup_already_queued" in (
                duplicate_response.headers["location"]
            )

        with patch.dict(
            os.environ,
            {"AUTOMATION_CRON_SECRET": ""},
            clear=False,
        ):
            unconfigured = asyncio.run(
                crm.run_background_jobs_cron(cron_request())
            )
            assert unconfigured.status_code == 503

        with patch.dict(
            os.environ,
            {"AUTOMATION_CRON_SECRET": "cron-smoke-secret"},
            clear=False,
        ):
            forbidden = asyncio.run(
                crm.run_background_jobs_cron(cron_request("wrong"))
            )
            assert forbidden.status_code == 403
            cron_result = asyncio.run(
                crm.run_background_jobs_cron(
                    cron_request("cron-smoke-secret")
                )
            )
            assert cron_result["ok"] is True
            assert cron_result["summary"]["succeeded"] == 1
            backup_filename = cron_result["summary"]["items"][0][
                "result"
            ]["filename"]
            assert (Path(temp_dir) / "backups" / backup_filename).is_file()

            enqueue_background_job(
                "test.unsupported",
                payload={},
                max_attempts=1,
            )
            failed_cron = asyncio.run(
                crm.run_background_jobs_cron(
                    cron_request("cron-smoke-secret")
                )
            )
            assert failed_cron.status_code == 503

        connection = database.connect()
        connection.execute(
            "DELETE FROM background_jobs WHERE status='failed'"
        )
        connection.commit()
        connection.close()

        final_status = get_background_queue_status()
        assert final_status["pending"] == 0
        assert final_status["running"] == 0
        assert final_status["status"] == "ok"

    print("Background job smoke passed.")


if __name__ == "__main__":
    main()

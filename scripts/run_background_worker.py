#!/usr/bin/env python3
"""Process durable background jobs once or as a polling worker."""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import run_background_job_batch  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Run the Field Service durable background queue.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep polling. Without this flag one batch is processed.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=5,
        help="Delay between polling cycles in watch mode.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Maximum jobs per batch. Defaults to BACKGROUND_JOB_BATCH_SIZE.",
    )
    args = parser.parse_args()
    poll_seconds = max(1, min(60, int(args.poll_seconds)))
    worker_id = (
        f"worker-{socket.gethostname()[:40]}-{os.getpid()}-"
        f"{uuid4().hex[:8]}"
    )
    final_exit_code = 0

    while True:
        summary = run_background_job_batch(
            worker_id=worker_id,
            limit=args.max_jobs,
        )
        has_activity = any(
            summary[key]
            for key in (
                "claimed",
                "recovered",
                "stale_failed",
                "cleaned",
            )
        )
        if has_activity or not args.watch:
            print(
                json.dumps(summary, ensure_ascii=False, sort_keys=True),
                flush=True,
            )
        if summary["failed"] or summary["stale_failed"]:
            final_exit_code = 1
        if not args.watch:
            return final_exit_code
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

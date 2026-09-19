#!/usr/bin/env python3
"""Dry-run-first sync of existing uploads and backups to configured S3."""

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.object_storage import (  # noqa: E402
    ObjectStorageError,
    get_object_storage_runtime_config,
    s3_object_exists,
    save_storage_path,
)


def collect_storage_files(data_dir):
    data_dir = Path(data_dir)
    groups = (
        (data_dir / "uploads", ""),
        (data_dir / "backups", "backups"),
    )
    result = []
    for root, key_prefix in groups:
        if not root.exists():
            continue
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(root).as_posix()
            key = f"{key_prefix}/{relative}" if key_prefix else relative
            result.append({
                "path": file_path,
                "key": key,
                "size": file_path.stat().st_size,
            })
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Sync existing application files to configured S3 storage.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("DATA_DIR", "."),
        help="Application DATA_DIR. Defaults to the DATA_DIR environment value.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Upload files. Without this flag the command is read-only.",
    )
    args = parser.parse_args()

    config = get_object_storage_runtime_config()
    files = collect_storage_files(args.data_dir)
    report = {
        "mode": "execute" if args.execute else "dry_run",
        "backend": config["configured_backend"],
        "configuration_valid": config["configuration_valid"],
        "files": len(files),
        "bytes": sum(item["size"] for item in files),
        "uploaded": 0,
        "verified": 0,
        "failed": 0,
        "can_execute": (
            config["configured_backend"] == "s3"
            and config["configuration_valid"]
        ),
    }
    if not args.execute:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    if not report["can_execute"]:
        report["error"] = "s3_configuration_invalid"
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1

    data_dir = Path(args.data_dir)
    for item in files:
        try:
            save_storage_path(item["path"], item["key"], data_dir)
            report["uploaded"] += 1
            if s3_object_exists(item["key"]):
                report["verified"] += 1
            else:
                report["failed"] += 1
        except (ObjectStorageError, ValueError, OSError):
            report["failed"] += 1
    report["ok"] = report["failed"] == 0
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

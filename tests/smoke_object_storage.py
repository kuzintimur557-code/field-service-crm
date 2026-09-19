import asyncio
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import object_storage  # noqa: E402


class FakeBody(io.BytesIO):
    pass


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.head_bucket_calls = []

    def upload_fileobj(self, file_object, bucket, key, **kwargs):
        self.objects[(bucket, key)] = {
            "body": file_object.read(),
            "content_type": kwargs.get("ExtraArgs", {}).get("ContentType", ""),
        }

    def upload_file(self, filename, bucket, key, **kwargs):
        self.objects[(bucket, key)] = {
            "body": Path(filename).read_bytes(),
            "content_type": "",
            "extra_args": kwargs.get("ExtraArgs", {}),
        }

    def get_object(self, Bucket, Key):
        item = self.objects[(Bucket, Key)]
        return {
            "Body": FakeBody(item["body"]),
            "ContentLength": len(item["body"]),
            "ContentType": item["content_type"],
        }

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)
        return {"ContentLength": len(self.objects[(Bucket, Key)]["body"])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        return {}

    def head_bucket(self, Bucket):
        self.head_bucket_calls.append(Bucket)
        return {}


def main():
    fake_client = FakeS3Client()
    environment = {
        "OBJECT_STORAGE_BACKEND": "s3",
        "S3_BUCKET": "private-smoke-bucket",
        "S3_REGION": "eu-test-1",
        "S3_ENDPOINT_URL": "https://private-storage.internal",
        "S3_PREFIX": "field-service/test",
        "S3_SERVER_SIDE_ENCRYPTION": "AES256",
        "AWS_ACCESS_KEY_ID": "private-access-key",
        "AWS_SECRET_ACCESS_KEY": "private-secret-key",
    }
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        environment,
        clear=False,
    ), patch.object(
        object_storage.importlib.util,
        "find_spec",
        return_value=object(),
    ), patch.object(
        object_storage,
        "_create_s3_client",
        return_value=fake_client,
    ):
        local_root = Path(temp_dir)
        os.environ["DATA_DIR"] = temp_dir
        runtime = object_storage.get_object_storage_runtime_config()
        assert runtime["configuration_valid"] is True
        assert runtime["configured_backend"] == "s3"
        serialized = repr(runtime)
        assert "private-smoke-bucket" not in serialized
        assert "private-storage.internal" not in serialized
        assert "private-access-key" not in serialized
        assert "private-secret-key" not in serialized

        payload = io.BytesIO(b"durable file")
        saved = object_storage.save_storage_fileobj(
            payload,
            "client_files/document.txt",
            local_root,
            "text/plain",
        )
        assert saved["backend"] == "s3"
        storage_key = "field-service/test/client_files/document.txt"
        assert fake_client.objects[("private-smoke-bucket", storage_key)][
            "body"
        ] == b"durable file"
        assert (local_root / "client_files/document.txt").read_bytes() == (
            b"durable file"
        )
        assert object_storage.storage_object_exists(
            "client_files/document.txt",
            local_root,
        ) is True
        assert object_storage.read_storage_bytes(
            "client_files/document.txt",
            local_root,
        ) == b"durable file"

        source = local_root / "backup.dump"
        source.write_bytes(b"backup archive")
        object_storage.save_storage_path(
            source,
            "backups/backup.dump",
            local_root,
        )
        assert fake_client.objects[(
            "private-smoke-bucket",
            "field-service/test/backups/backup.dump",
        )]["body"] == b"backup archive"
        assert fake_client.objects[(
            "private-smoke-bucket",
            "field-service/test/backups/backup.dump",
        )]["extra_args"] == {"ServerSideEncryption": "AES256"}

        status = object_storage.get_object_storage_status(local_root)
        assert status["ok"] is True
        assert status["backend"] == "s3"
        assert fake_client.head_bucket_calls == ["private-smoke-bucket"]

        object_storage.delete_storage_object(
            "client_files/document.txt",
            local_root,
        )
        assert ("private-smoke-bucket", storage_key) not in fake_client.objects
        assert not (local_root / "client_files/document.txt").exists()

        from app import main as crm

        upload = SimpleNamespace(
            filename="photo.jpg",
            content_type="image/jpeg",
            file=io.BytesIO(b"route photo"),
        )
        stored_filename = crm.save_upload_file(upload, 42, "before")
        assert stored_filename.startswith("task_42_before_")
        assert object_storage.s3_object_exists(stored_filename) is True
        response = crm.storage_file_response(stored_filename, crm.UPLOAD_DIR)
        assert response.status_code == 200

        async def response_body():
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return b"".join(chunks)

        assert asyncio.run(response_body()) == b"route photo"

        backup_dir = crm.DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / "smoke.dump"
        backup_file.write_bytes(b"dump")
        Path(f"{backup_file}.json").write_text("{}", encoding="utf-8")
        assert crm.mirror_database_backup(backup_file.name) == ""
        assert object_storage.s3_object_exists("backups/smoke.dump") is True
        assert object_storage.s3_object_exists(
            "backups/smoke.dump.json"
        ) is True

        from scripts.sync_files_to_s3 import collect_storage_files

        collected_keys = {
            item["key"]
            for item in collect_storage_files(crm.DATA_DIR)
        }
        assert stored_filename in collected_keys
        assert "backups/smoke.dump" in collected_keys
        assert "backups/smoke.dump.json" in collected_keys

        for invalid_key in ("../secret", "/absolute", "bad\\key"):
            try:
                object_storage.storage_object_exists(invalid_key, local_root)
            except ValueError:
                pass
            else:
                raise AssertionError(f"unsafe key accepted: {invalid_key}")

    with patch.dict(
        os.environ,
        {"OBJECT_STORAGE_BACKEND": "s3", "S3_BUCKET": ""},
        clear=False,
    ):
        invalid = object_storage.get_object_storage_runtime_config()
        assert invalid["configuration_valid"] is False
        assert "s3_bucket_required" in invalid["errors"]

    print("Object storage smoke passed.")


if __name__ == "__main__":
    main()

"""Local and S3-compatible storage for user files and backup mirrors."""

import importlib.util
import os
import shutil
from pathlib import Path, PurePosixPath


LOCAL_BACKEND = "local"
S3_BACKEND = "s3"


class ObjectStorageError(RuntimeError):
    """A safe storage failure that never contains provider credentials."""


def _environment_bool(name, default=False):
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def _normalize_prefix(value):
    prefix = str(value or "").strip().strip("/")
    if not prefix:
        return ""
    _safe_relative_key(prefix)
    return prefix


def _safe_relative_key(value):
    key = str(value or "").strip()
    if not key or "\\" in key or "//" in key or key.startswith("/"):
        raise ValueError("Invalid object storage key")
    path = PurePosixPath(key)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Invalid object storage key")
    return path.as_posix()


def get_object_storage_runtime_config():
    """Return safe configuration metadata without endpoint or credentials."""
    raw_backend = str(
        os.getenv("OBJECT_STORAGE_BACKEND") or LOCAL_BACKEND
    ).strip().lower()
    backend = {"filesystem": LOCAL_BACKEND, "aws": S3_BACKEND}.get(
        raw_backend,
        raw_backend,
    )
    bucket = str(os.getenv("S3_BUCKET") or "").strip()
    region = str(os.getenv("S3_REGION") or "").strip()
    endpoint_configured = bool(str(os.getenv("S3_ENDPOINT_URL") or "").strip())
    driver_available = bool(importlib.util.find_spec("boto3"))
    errors = []
    try:
        prefix = _normalize_prefix(os.getenv("S3_PREFIX"))
    except ValueError:
        prefix = ""
        errors.append("invalid_s3_prefix")

    if backend not in {LOCAL_BACKEND, S3_BACKEND}:
        errors.append("unsupported_object_storage_backend")
    if backend == S3_BACKEND:
        if not bucket:
            errors.append("s3_bucket_required")
        if not driver_available:
            errors.append("boto3_missing")

    return {
        "configured_backend": backend,
        "configured_backend_label": (
            "S3-совместимое" if backend == S3_BACKEND else "Локальное"
        ),
        "configuration_valid": not errors,
        "errors": errors,
        "bucket_configured": bool(bucket),
        "region_configured": bool(region),
        "endpoint_configured": endpoint_configured,
        "prefix_configured": bool(prefix),
        "driver_available": driver_available,
        "cache_local_files": _environment_bool("S3_LOCAL_CACHE", True),
        "server_side_encryption_configured": bool(
            str(os.getenv("S3_SERVER_SIDE_ENCRYPTION") or "").strip()
        ),
    }


def _validated_configuration():
    config = get_object_storage_runtime_config()
    if not config["configuration_valid"]:
        raise ObjectStorageError("object_storage_configuration_invalid")
    return config


def _local_path(local_root, relative_key):
    key = _safe_relative_key(relative_key)
    root = Path(local_root).resolve()
    path = (root / Path(*PurePosixPath(key).parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("Invalid object storage key") from error
    return path


def _s3_key(relative_key):
    key = _safe_relative_key(relative_key)
    prefix = _normalize_prefix(os.getenv("S3_PREFIX"))
    return f"{prefix}/{key}" if prefix else key


def _create_s3_client():
    import boto3

    kwargs = {}
    region = str(os.getenv("S3_REGION") or "").strip()
    endpoint = str(os.getenv("S3_ENDPOINT_URL") or "").strip()
    addressing_style = str(
        os.getenv("S3_ADDRESSING_STYLE") or ""
    ).strip().lower()
    if region:
        kwargs["region_name"] = region
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if addressing_style in {"auto", "path", "virtual"}:
        from botocore.config import Config

        kwargs["config"] = Config(
            s3={"addressing_style": addressing_style},
            retries={"max_attempts": 3, "mode": "standard"},
        )
    return boto3.client("s3", **kwargs)


def _upload_extra_args(content_type=""):
    result = {}
    if content_type:
        result["ContentType"] = str(content_type)[:255]
    encryption = str(
        os.getenv("S3_SERVER_SIDE_ENCRYPTION") or ""
    ).strip()
    kms_key_id = str(os.getenv("S3_KMS_KEY_ID") or "").strip()
    if encryption:
        result["ServerSideEncryption"] = encryption
    if encryption == "aws:kms" and kms_key_id:
        result["SSEKMSKeyId"] = kms_key_id
    return result


def _rewind(file_object):
    try:
        file_object.seek(0)
    except (AttributeError, OSError):
        pass


def _write_local_cache(file_object, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    _rewind(file_object)
    with open(path, "wb") as target:
        shutil.copyfileobj(file_object, target)
    _rewind(file_object)


def save_storage_fileobj(
    file_object,
    relative_key,
    local_root,
    content_type="",
):
    """Persist a binary file object to local or S3 storage."""
    config = _validated_configuration()
    local_path = _local_path(local_root, relative_key)
    if config["configured_backend"] == LOCAL_BACKEND:
        try:
            _write_local_cache(file_object, local_path)
        except (OSError, ValueError) as error:
            raise ObjectStorageError("local_storage_write_failed") from error
        return {"backend": LOCAL_BACKEND, "key": relative_key}

    try:
        _rewind(file_object)
        extra_args = _upload_extra_args(content_type)
        upload_kwargs = {"ExtraArgs": extra_args} if extra_args else {}
        _create_s3_client().upload_fileobj(
            file_object,
            os.getenv("S3_BUCKET"),
            _s3_key(relative_key),
            **upload_kwargs,
        )
    except Exception as error:
        raise ObjectStorageError("s3_storage_write_failed") from error

    if config["cache_local_files"]:
        try:
            _write_local_cache(file_object, local_path)
        except (OSError, ValueError):
            pass
    return {"backend": S3_BACKEND, "key": relative_key}


def save_storage_path(source_path, relative_key, local_root):
    source_path = Path(source_path)
    if not source_path.is_file():
        raise ObjectStorageError("storage_source_missing")
    config = _validated_configuration()
    if config["configured_backend"] == LOCAL_BACKEND:
        destination = _local_path(local_root, relative_key)
        if source_path.resolve() != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
        return {"backend": LOCAL_BACKEND, "key": relative_key}
    try:
        extra_args = _upload_extra_args()
        upload_kwargs = {"ExtraArgs": extra_args} if extra_args else {}
        _create_s3_client().upload_file(
            str(source_path),
            os.getenv("S3_BUCKET"),
            _s3_key(relative_key),
            **upload_kwargs,
        )
    except Exception as error:
        raise ObjectStorageError("s3_storage_write_failed") from error
    return {"backend": S3_BACKEND, "key": relative_key}


def get_storage_object(relative_key, local_root):
    """Return a local path or S3 StreamingBody, with local migration fallback."""
    config = get_object_storage_runtime_config()
    local_path = _local_path(local_root, relative_key)
    if config["configured_backend"] == S3_BACKEND and config["configuration_valid"]:
        try:
            response = _create_s3_client().get_object(
                Bucket=os.getenv("S3_BUCKET"),
                Key=_s3_key(relative_key),
            )
            return {
                "backend": S3_BACKEND,
                "body": response["Body"],
                "content_type": response.get("ContentType") or "",
                "content_length": int(response.get("ContentLength") or 0),
                "etag": str(response.get("ETag") or "").strip(),
            }
        except Exception:
            pass
    if local_path.is_file():
        stat = local_path.stat()
        return {
            "backend": LOCAL_BACKEND,
            "path": local_path,
            "content_type": "",
            "content_length": stat.st_size,
            "etag": f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"',
        }
    return None


def storage_object_exists(relative_key, local_root):
    config = get_object_storage_runtime_config()
    if config["configured_backend"] == S3_BACKEND and config["configuration_valid"]:
        try:
            _create_s3_client().head_object(
                Bucket=os.getenv("S3_BUCKET"),
                Key=_s3_key(relative_key),
            )
            return True
        except Exception:
            pass
    return _local_path(local_root, relative_key).is_file()


def s3_object_exists(relative_key):
    """Check only the remote object, without the local migration fallback."""
    config = get_object_storage_runtime_config()
    if config["configured_backend"] != S3_BACKEND:
        return False
    if not config["configuration_valid"]:
        return False
    try:
        _create_s3_client().head_object(
            Bucket=os.getenv("S3_BUCKET"),
            Key=_s3_key(relative_key),
        )
        return True
    except Exception:
        return False


def delete_storage_object(relative_key, local_root):
    config = _validated_configuration()
    remote_error = None
    if config["configured_backend"] == S3_BACKEND:
        try:
            _create_s3_client().delete_object(
                Bucket=os.getenv("S3_BUCKET"),
                Key=_s3_key(relative_key),
            )
        except Exception as error:
            remote_error = error
    local_path = _local_path(local_root, relative_key)
    try:
        local_path.unlink()
    except FileNotFoundError:
        pass
    except OSError as error:
        if config["configured_backend"] == LOCAL_BACKEND:
            raise ObjectStorageError("local_storage_delete_failed") from error
    if remote_error is not None:
        raise ObjectStorageError("s3_storage_delete_failed") from remote_error


def read_storage_bytes(relative_key, local_root, maximum_bytes=25 * 1024 * 1024):
    stored = get_storage_object(relative_key, local_root)
    if stored is None:
        return None
    if stored["content_length"] > maximum_bytes:
        raise ObjectStorageError("storage_object_too_large")
    if stored["backend"] == LOCAL_BACKEND:
        try:
            return stored["path"].read_bytes()
        except OSError as error:
            raise ObjectStorageError("local_storage_read_failed") from error
    body = stored["body"]
    try:
        data = body.read(maximum_bytes + 1)
        if len(data) > maximum_bytes:
            raise ObjectStorageError("storage_object_too_large")
        return data
    except ObjectStorageError:
        raise
    except Exception as error:
        raise ObjectStorageError("s3_storage_read_failed") from error
    finally:
        try:
            body.close()
        except Exception:
            pass


def get_object_storage_status(local_root, check_remote=True):
    config = get_object_storage_runtime_config()
    backend = config["configured_backend"]
    if not config["configuration_valid"]:
        return {
            "ok": False,
            "status": "critical",
            "status_label": "Ошибка конфигурации",
            "backend": backend,
            "backend_label": config["configured_backend_label"],
            "message": "Конфигурация файлового хранилища неполна.",
            "configuration": config,
        }
    if backend == LOCAL_BACKEND:
        root = Path(local_root)
        available = root.exists() and os.access(root, os.W_OK)
        return {
            "ok": available,
            "status": "ok" if available else "critical",
            "status_label": "Доступно" if available else "Недоступно",
            "backend": backend,
            "backend_label": "Локальное",
            "message": (
                "Локальная папка файлов доступна для записи."
                if available
                else "Локальная папка файлов недоступна для записи."
            ),
            "configuration": config,
        }
    if not check_remote:
        return {
            "ok": True,
            "status": "ok",
            "status_label": "Настроено",
            "backend": backend,
            "backend_label": "S3-совместимое",
            "message": "S3-совместимое хранилище настроено.",
            "configuration": config,
        }
    try:
        _create_s3_client().head_bucket(Bucket=os.getenv("S3_BUCKET"))
        available = True
    except Exception:
        available = False
    return {
        "ok": available,
        "status": "ok" if available else "critical",
        "status_label": "Доступно" if available else "Недоступно",
        "backend": backend,
        "backend_label": "S3-совместимое",
        "message": (
            "S3 bucket доступен приложению."
            if available
            else "S3 bucket недоступен или не хватает прав."
        ),
        "configuration": config,
    }

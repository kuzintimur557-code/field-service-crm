"""Upload validation, safe filenames and storage file responses."""

import mimetypes
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi.responses import FileResponse, Response, StreamingResponse

from app.database import DATA_DIR
from app.object_storage import (
    ObjectStorageError,
    get_storage_object,
    save_storage_fileobj,
)

UPLOAD_DIR = DATA_DIR / "uploads"
DOCS_DIR = UPLOAD_DIR / "docs"
CLIENT_FILES_DIR = UPLOAD_DIR / "client_files"
CALL_AUDIO_DIR = UPLOAD_DIR / "call_audio"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
CLIENT_FILE_UPLOAD_MAX_BYTES = 25 * 1024 * 1024
CALL_AUDIO_UPLOAD_MAX_BYTES = 50 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_CLIENT_FILE_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx",
    ".xls", ".xlsx", ".csv", ".txt"
}
ALLOWED_CALL_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".aac", ".mp4"}
PDF_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

class UploadValidationError(ObjectStorageError):
    def __init__(self, code):
        super().__init__(str(code or "invalid_upload"))
        self.code = str(code or "invalid_upload")


def get_upload_size(upload_file):
    file_object = getattr(upload_file, "file", None)
    if file_object is None:
        raise UploadValidationError("invalid")
    try:
        position = file_object.tell()
        file_object.seek(0, 2)
        size = file_object.tell()
        file_object.seek(position)
    except (AttributeError, OSError, ValueError) as error:
        raise UploadValidationError("invalid") from error
    return max(0, int(size))


def validate_upload_file(upload_file, allowed_extensions, maximum_bytes):
    if not upload_file or not getattr(upload_file, "filename", ""):
        raise UploadValidationError("empty")
    extension = Path(Path(upload_file.filename).name).suffix.lower()
    if extension not in allowed_extensions:
        raise UploadValidationError("type")
    if get_upload_size(upload_file) > maximum_bytes:
        raise UploadValidationError("size")
    return extension


def safe_upload_filename(task_id, prefix, original_filename):
    original = Path(original_filename or "photo").name
    extension = Path(original).suffix.lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        extension = ".jpg"

    return f"task_{task_id}_{prefix}_{uuid4().hex}{extension}"


def save_upload_file(upload_file, task_id, prefix):
    if not upload_file or not upload_file.filename:
        return ""

    extension = validate_upload_file(
        upload_file,
        ALLOWED_IMAGE_EXTENSIONS,
        IMAGE_UPLOAD_MAX_BYTES,
    )
    filename = safe_upload_filename(task_id, prefix, upload_file.filename)
    save_storage_fileobj(
        upload_file.file,
        filename,
        UPLOAD_DIR,
        IMAGE_CONTENT_TYPES[extension],
    )

    return filename


def storage_file_response(
    relative_key,
    local_root,
    download_name="",
    media_type="",
    request=None,
):
    try:
        stored = get_storage_object(relative_key, local_root)
    except (ObjectStorageError, ValueError):
        stored = None
    if stored is None:
        return Response(status_code=404)

    etag = str(stored.get("etag") or "").strip()
    cache_headers = {"Cache-Control": "private, max-age=86400"}
    if etag:
        cache_headers["ETag"] = etag

    if etag and request is not None:
        client_etags = (
            request.headers.get("if-none-match") or ""
        ).split(",")
        if any(client_tag.strip() == etag for client_tag in client_etags):
            return Response(status_code=304, headers=cache_headers)

    safe_download_name = Path(download_name or "").name
    guessed_media_type = mimetypes.guess_type(relative_key)[0] or ""
    resolved_media_type = (
        media_type
        or (
            ""
            if stored["content_type"] == "application/octet-stream"
            else stored["content_type"]
        )
        or guessed_media_type
        or "application/octet-stream"
    )
    if stored["backend"] == "local":
        return FileResponse(
            str(stored["path"]),
            filename=safe_download_name or None,
            media_type=resolved_media_type,
            headers=cache_headers,
        )

    body = stored["body"]

    def stream_body():
        try:
            while True:
                chunk = body.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                body.close()
            except Exception:
                pass

    headers = dict(cache_headers)
    if stored["content_length"]:
        headers["Content-Length"] = str(stored["content_length"])
    if safe_download_name:
        headers["Content-Disposition"] = (
            "attachment; filename*=UTF-8''" + quote(safe_download_name)
        )
    return StreamingResponse(
        stream_body(),
        media_type=resolved_media_type,
        headers=headers,
    )


def safe_client_file_filename(client_id, original_filename):
    original = Path(original_filename or "file").name
    extension = Path(original).suffix.lower()

    if extension not in ALLOWED_CLIENT_FILE_EXTENSIONS:
        extension = ".bin"

    return f"client_{client_id}_{uuid4().hex}{extension}"


def safe_call_audio_filename(call_id, original_filename):
    original = Path(original_filename or "audio").name
    extension = Path(original).suffix.lower()

    if extension not in ALLOWED_CALL_AUDIO_EXTENSIONS:
        extension = ".mp3"

    return f"call_{call_id}_{uuid4().hex}{extension}"

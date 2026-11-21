# Copyright Advanced Software and AI Solutions LLC
"""Upload validation, Host/Origin checks, and extraction lock."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import EXTRACT_LOCK_WAIT_S

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
WEBP_RIFF = b"RIFF"
WEBP_WEBP = b"WEBP"
PDF_MAGIC = b"%PDF"


@dataclass(frozen=True)
class DetectedFile:
    kind: str  # png | jpeg | webp | pdf
    mime: str


class UploadValidationError(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def detect_file_type(data: bytes) -> DetectedFile:
    if len(data) >= 8 and data[:8] == PNG_MAGIC:
        return DetectedFile("png", "image/png")
    if len(data) >= 3 and data[:3] == JPEG_MAGIC:
        return DetectedFile("jpeg", "image/jpeg")
    if len(data) >= 12 and data[:4] == WEBP_RIFF and data[8:12] == WEBP_WEBP:
        return DetectedFile("webp", "image/webp")
    if len(data) >= 4 and data[:4] == PDF_MAGIC:
        return DetectedFile("pdf", "application/pdf")
    raise UploadValidationError(
        415,
        "unsupported_media",
        "File must be PNG, JPEG, WebP, or PDF (checked by magic bytes).",
    )


async def read_upload_limited(upload, max_bytes: int) -> bytes:
    """Read an UploadFile while enforcing a byte limit."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadValidationError(
                413,
                "payload_too_large",
                f"Upload exceeds the maximum size of {max_bytes} bytes.",
            )
        chunks.append(chunk)
    if not chunks:
        raise UploadValidationError(400, "empty_upload", "Uploaded file is empty.")
    return b"".join(chunks)


def _normalize_host(value: str) -> str:
    return value.strip().lower()


def host_allowed(request_host: str | None, app_host: str, app_port: int) -> bool:
    if not request_host:
        return False
    host = _normalize_host(request_host)
    names = {
        _normalize_host(app_host),
        "localhost",
        "127.0.0.1",
        "[::1]",
        "::1",
    }
    allowed = set()
    for name in names:
        allowed.add(name)
        allowed.add(f"{name}:{app_port}")
    return host in allowed


def origin_allowed(origin: str | None, app_host: str, app_port: int) -> bool:
    if origin is None or origin == "":
        return True
    origin = origin.strip().rstrip("/")
    names = {_normalize_host(app_host), "localhost", "127.0.0.1"}
    candidates: set[str] = set()
    for name in names:
        candidates.add(f"http://{name}:{app_port}")
        candidates.add(f"https://{name}:{app_port}")
        if app_port == 80:
            candidates.add(f"http://{name}")
        if app_port == 443:
            candidates.add(f"https://{name}")
    return origin.lower() in {c.lower() for c in candidates}


class ExtractionLock:
    """Allow one extraction at a time; wait up to EXTRACT_LOCK_WAIT_S then fail."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=EXTRACT_LOCK_WAIT_S)
            return True
        except TimeoutError:
            return False

    def release(self) -> None:
        if self._lock.locked():
            self._lock.release()


extract_lock = ExtractionLock()

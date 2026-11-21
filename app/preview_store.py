# Copyright Advanced Software and AI Solutions LLC
"""In-memory snapshot of the last validated upload for page PNG previews."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class PreviewSnapshot:
    data: bytes
    kind: str  # png | jpeg | webp | pdf
    page_count: int


_lock = Lock()
_snapshot: PreviewSnapshot | None = None


def clear() -> None:
    global _snapshot
    with _lock:
        _snapshot = None


def set_snapshot(data: bytes, kind: str, page_count: int) -> None:
    global _snapshot
    with _lock:
        _snapshot = PreviewSnapshot(data=data, kind=kind, page_count=page_count)


def get_snapshot() -> PreviewSnapshot | None:
    with _lock:
        return _snapshot

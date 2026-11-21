# Copyright Advanced Software and AI Solutions LLC
"""Validate local file paths before uploading to the OCR API."""

from __future__ import annotations

import os
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MAX_PATH_CHARS = 1024


class PathValidationError(Exception):
    """Path rejected before any upload."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _strip_surrounding_quotes(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip()
    return text


def _looks_like_unc_or_device(path_text: str) -> bool:
    # Reject UNC and Windows device paths before resolve.
    if path_text.startswith("\\\\?") or path_text.startswith("//?"):
        return True
    if path_text.startswith("\\\\.") or path_text.startswith("//."):
        return True
    # \\server\share or //server/...
    if path_text.startswith("\\\\") or path_text.startswith("//"):
        return True
    return False


def _is_under_root(root: Path, path: Path) -> bool:
    root_s = os.path.normcase(str(root))
    path_s = os.path.normcase(str(path))
    if path_s == root_s:
        return True
    prefix = root_s if root_s.endswith(os.sep) else root_s + os.sep
    return path_s.startswith(prefix)


def allowed_roots_from_env(raw: str | None = None) -> list[Path] | None:
    value = raw if raw is not None else os.environ.get("OCR_ALLOWED_ROOTS")
    if value is None or str(value).strip() == "":
        return None
    roots: list[Path] = []
    for part in str(value).split(os.pathsep):
        item = part.strip().strip('"').strip("'")
        if not item:
            continue
        roots.append(Path(item).expanduser())
    return roots or None


def validate_ocr_path(
    raw_path: str,
    *,
    max_upload_mb: int,
    allowed_roots: list[Path] | None = None,
) -> tuple[Path, bytes]:
    """Validate path and read the file once into memory.

    Returns (resolved_path, file_bytes). Never writes files.
    """
    if not isinstance(raw_path, str):
        raise PathValidationError("invalid_path", "path must be a string.")
    if len(raw_path) > MAX_PATH_CHARS:
        raise PathValidationError(
            "invalid_path",
            f"path must be at most {MAX_PATH_CHARS} characters.",
        )

    cleaned = _strip_surrounding_quotes(raw_path)
    if not cleaned:
        raise PathValidationError("invalid_path", "path is empty.")
    if _looks_like_unc_or_device(cleaned):
        raise PathValidationError(
            "invalid_path",
            "UNC and device paths are not allowed.",
        )

    expanded = Path(cleaned).expanduser()
    if not expanded.is_absolute():
        raise PathValidationError(
            "invalid_path",
            "path must be an absolute filesystem path; relative paths are not allowed.",
        )

    try:
        resolved = expanded.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PathValidationError("invalid_path", "path does not exist.") from exc
    except OSError as exc:
        raise PathValidationError("invalid_path", "path could not be resolved.") from exc

    # Re-check after resolve (symlink / normalization)
    resolved_text = str(resolved)
    if _looks_like_unc_or_device(resolved_text):
        raise PathValidationError(
            "invalid_path",
            "UNC and device paths are not allowed.",
        )

    if not resolved.is_file():
        raise PathValidationError("invalid_path", "path must be a regular file.")

    suffix = resolved.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise PathValidationError(
            "invalid_path",
            "file extension must be .pdf, .png, .jpg, .jpeg, or .webp.",
        )

    roots = allowed_roots if allowed_roots is not None else allowed_roots_from_env()
    if roots is not None:
        ok = False
        for root in roots:
            try:
                root_resolved = root.resolve(strict=False)
            except OSError:
                continue
            if _is_under_root(root_resolved, resolved):
                ok = True
                break
        if not ok:
            raise PathValidationError(
                "invalid_path",
                "path is outside OCR_ALLOWED_ROOTS.",
            )

    max_bytes = max(1, int(max_upload_mb)) * 1024 * 1024
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise PathValidationError("invalid_path", "could not read file size.") from exc
    if size > max_bytes:
        raise PathValidationError(
            "file_too_large",
            f"file exceeds maxUploadMb ({max_upload_mb}).",
        )

    try:
        data = resolved.read_bytes()
    except OSError as exc:
        raise PathValidationError("invalid_path", "could not read file.") from exc
    if len(data) > max_bytes:
        raise PathValidationError(
            "file_too_large",
            f"file exceeds maxUploadMb ({max_upload_mb}).",
        )
    return resolved, data

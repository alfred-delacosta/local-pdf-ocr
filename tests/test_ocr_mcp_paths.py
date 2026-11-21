# Copyright Advanced Software and AI Solutions LLC
"""Path validation for ocr_file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ocr_mcp.paths import PathValidationError, validate_ocr_path


def _write(tmp_path: Path, name: str, data: bytes = b"hello") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_absolute_ok_and_uppercase_ext(tmp_path):
    path = _write(tmp_path, "Scan.PDF", b"%PDF-1.4")
    resolved, data = validate_ocr_path(str(path), max_upload_mb=1)
    assert resolved == path.resolve()
    assert data.startswith(b"%PDF")


def test_quotes_stripped(tmp_path):
    path = _write(tmp_path, "a.png", b"\x89PNG\r\n\x1a\n")
    resolved, _ = validate_ocr_path(f'"{path}"', max_upload_mb=1)
    assert resolved == path.resolve()


def test_relative_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "a.pdf")
    with pytest.raises(
        PathValidationError,
        match="path must be an absolute filesystem path; relative paths are not allowed",
    ):
        validate_ocr_path("a.pdf", max_upload_mb=1)


def test_unc_rejected():
    with pytest.raises(PathValidationError, match="UNC"):
        validate_ocr_path(r"\\server\share\file.pdf", max_upload_mb=1)


def test_device_path_rejected():
    with pytest.raises(PathValidationError, match="UNC|device"):
        validate_ocr_path(r"\\.\pipe\ocr", max_upload_mb=1)


def test_missing_rejected(tmp_path):
    missing = tmp_path / "missing.pdf"
    with pytest.raises(PathValidationError, match="does not exist"):
        validate_ocr_path(str(missing), max_upload_mb=1)


def test_folder_rejected(tmp_path):
    with pytest.raises(PathValidationError, match="regular file"):
        validate_ocr_path(str(tmp_path), max_upload_mb=1)


def test_wrong_extension_rejected(tmp_path):
    path = _write(tmp_path, "evil.exe", b"MZ")
    with pytest.raises(PathValidationError, match="extension"):
        validate_ocr_path(str(path), max_upload_mb=1)


def test_oversize_rejected(tmp_path):
    path = _write(tmp_path, "big.pdf", b"x" * (2 * 1024 * 1024))
    with pytest.raises(PathValidationError) as exc:
        validate_ocr_path(str(path), max_upload_mb=1)
    assert exc.value.code == "file_too_large"


def test_outside_allowed_roots(tmp_path):
    inside = tmp_path / "allowed"
    outside = tmp_path / "other"
    inside.mkdir()
    outside.mkdir()
    path = _write(outside, "a.pdf")
    with pytest.raises(PathValidationError, match="OCR_ALLOWED_ROOTS"):
        validate_ocr_path(
            str(path),
            max_upload_mb=1,
            allowed_roots=[inside],
        )


def test_inside_allowed_roots(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    path = _write(root, "a.webp", b"RIFF")
    resolved, _ = validate_ocr_path(str(path), max_upload_mb=1, allowed_roots=[root])
    assert resolved == path.resolve()


@pytest.mark.skipif(os.name != "nt", reason="Windows symlink case")
def test_symlink_outside_roots(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    target = _write(outside, "secret.pdf")
    link = allowed / "link.pdf"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink privilege not available")
    with pytest.raises(PathValidationError, match="OCR_ALLOWED_ROOTS"):
        validate_ocr_path(str(link), max_upload_mb=1, allowed_roots=[allowed])

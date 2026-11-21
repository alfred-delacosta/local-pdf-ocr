# Copyright Advanced Software and AI Solutions LLC
"""Shared pytest fixtures."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.config as config_mod
import app.settings_store as settings_mod
from app.main import create_app


def make_png_bytes(color=(20, 40, 60), size=(64, 48)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_text_pdf(text: str = "Hello digital PDF text layer content for OCR skip test.") -> bytes:
    """Build a tiny single-page PDF with a Helvetica text layer."""
    # Escape PDF string literals
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 40 100 Td ({safe}) Tj ET"
    stream_bytes = stream.encode("latin-1")
    objects = []
    objects.append("1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append("2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(f"4 0 obj<< /Length {len(stream_bytes)} >>stream\n{stream}\nendstream\nendobj\n")
    objects.append("5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for obj in objects:
        offsets.append(sum(len(p) for p in parts))
        parts.append(obj.encode("latin-1"))
    xref_pos = sum(len(p) for p in parts)
    xref = [f"xref\n0 {len(offsets)}\n", "0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n")
    trailer = f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    parts.append("".join(xref).encode("latin-1"))
    parts.append(trailer.encode("latin-1"))
    data = b"".join(parts)
    assert len(data) < 50_000
    return data


def make_blank_pdf(pages: int = 1) -> bytes:
    """Multi-page PDF with empty content streams (image-only / no usable text)."""
    next_id = 3
    page_ids: list[int] = []
    page_objs: list[str] = []
    content_objs: list[str] = []
    for _ in range(pages):
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        page_objs.append(
            f"{page_id} 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            f"/Contents {content_id} 0 R >>endobj\n"
        )
        content_objs.append(f"{content_id} 0 obj<< /Length 0 >>stream\n\nendstream\nendobj\n")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    ordered: list[str] = [
        "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        f"2 0 obj<< /Type /Pages /Kids [{kids}] /Count {pages} >>endobj\n",
    ]
    for ptxt, ctxt in zip(page_objs, content_objs, strict=True):
        ordered.append(ptxt)
        ordered.append(ctxt)

    parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for obj in ordered:
        offsets.append(sum(len(p) for p in parts))
        parts.append(obj.encode("latin-1"))
    xref_pos = sum(len(p) for p in parts)
    xref = [f"xref\n0 {len(offsets)}\n", "0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n")
    trailer = f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    parts.append("".join(xref).encode("latin-1"))
    parts.append(trailer.encode("latin-1"))
    data = b"".join(parts)
    assert len(data) < 50_000
    return data


@pytest.fixture()
def png_bytes() -> bytes:
    return make_png_bytes()


@pytest.fixture()
def text_pdf_bytes() -> bytes:
    return make_text_pdf()


@pytest.fixture()
def blank_pdf_bytes() -> bytes:
    return make_blank_pdf(1)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(config_mod, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", settings_path)
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "3000")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("MODEL_ID", "LightOnOCR-3-0.8B")
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("MAX_PAGES", "5")
    monkeypatch.setenv("LMSTUDIO_TIMEOUT_S", "5")
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:3000") as test_client:
        yield test_client

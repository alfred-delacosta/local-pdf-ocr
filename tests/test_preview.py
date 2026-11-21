# Copyright Advanced Software and AI Solutions LLC

from __future__ import annotations

import json

import httpx
import respx

from app.security import PNG_MAGIC
from tests.conftest import make_blank_pdf


def _ocr_route():
    return respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "OCR markdown text"}},
                ]
            },
        )
    )


def test_preview_unavailable_before_extract(client):
    resp = client.get("/api/preview/pages/1")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "preview_unavailable"


@respx.mock
def test_preview_png_after_pdf_extract(client, text_pdf_bytes):
    _ocr_route()
    extract = client.post(
        "/api/extract",
        files={"file": ("doc.pdf", text_pdf_bytes, "application/pdf")},
    )
    assert extract.status_code == 200
    assert "previewJobId" not in extract.json()

    resp = client.get("/api/preview/pages/1")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content[:8] == PNG_MAGIC


@respx.mock
def test_preview_page_out_of_range(client, text_pdf_bytes):
    _ocr_route()
    extract = client.post(
        "/api/extract",
        files={"file": ("doc.pdf", text_pdf_bytes, "application/pdf")},
    )
    assert extract.status_code == 200

    resp = client.get("/api/preview/pages/99")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "page_not_found"


@respx.mock
def test_preview_after_image_extract(client, png_bytes):
    _ocr_route()
    extract = client.post(
        "/api/extract",
        files={"file": ("page.png", png_bytes, "image/png")},
    )
    assert extract.status_code == 200

    resp = client.get("/api/preview/pages/1")
    assert resp.status_code == 200
    assert resp.content[:8] == PNG_MAGIC

    missing = client.get("/api/preview/pages/2")
    assert missing.status_code == 404


@respx.mock
def test_ndjson_done_has_no_preview_job_id(client, blank_pdf_bytes):
    _ocr_route()
    resp = client.post(
        "/api/extract",
        headers={"Accept": "application/x-ndjson"},
        files={"file": ("scan.pdf", blank_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    lines = [line for line in resp.text.splitlines() if line.strip()]
    done = json.loads(lines[-1])
    assert done["type"] == "done"
    assert "previewJobId" not in done
    assert "text" in done
    assert "pages" in done

    preview = client.get("/api/preview/pages/1")
    assert preview.status_code == 200
    assert preview.content[:8] == PNG_MAGIC


@respx.mock
def test_preview_cleared_when_new_extract_starts(client, text_pdf_bytes, png_bytes):
    _ocr_route()
    first = client.post(
        "/api/extract",
        files={"file": ("doc.pdf", text_pdf_bytes, "application/pdf")},
    )
    assert first.status_code == 200
    assert client.get("/api/preview/pages/1").status_code == 200

    # Multi-page PDF then switch to a single image: page 2 must disappear.
    multi = make_blank_pdf(2)
    second = client.post(
        "/api/extract",
        files={"file": ("multi.pdf", multi, "application/pdf")},
    )
    assert second.status_code == 200
    assert client.get("/api/preview/pages/2").status_code == 200

    third = client.post(
        "/api/extract",
        files={"file": ("page.png", png_bytes, "image/png")},
    )
    assert third.status_code == 200
    assert client.get("/api/preview/pages/1").status_code == 200
    assert client.get("/api/preview/pages/2").status_code == 404

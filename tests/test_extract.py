# Copyright Advanced Software and AI Solutions LLC

from __future__ import annotations

import json
import logging

import httpx
import respx

from tests.conftest import make_blank_pdf, make_png_bytes


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


@respx.mock
def test_extract_text_layer_pdf_no_model_call(client, text_pdf_bytes):
    route = _ocr_route()
    resp = client.post(
        "/api/extract",
        files={"file": ("doc.pdf", text_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pages"][0]["source"] == "text-layer"
    assert "Hello digital PDF" in body["text"]
    assert route.call_count == 0


@respx.mock
def test_extract_blank_pdf_calls_model(client, blank_pdf_bytes):
    route = _ocr_route()
    resp = client.post(
        "/api/extract",
        files={"file": ("scan.pdf", blank_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pages"][0]["source"] == "ocr"
    assert body["text"] == "OCR markdown text"
    assert route.call_count == 1


@respx.mock
def test_extract_png(client, png_bytes):
    _ocr_route()
    resp = client.post(
        "/api/extract",
        files={"file": ("page.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file"]["type"] == "png"
    assert body["pages"][0]["source"] == "ocr"


@respx.mock
def test_force_ocr_on_text_pdf(client, text_pdf_bytes):
    route = _ocr_route()
    resp = client.post(
        "/api/extract",
        data={"forceOcr": "true"},
        files={"file": ("doc.pdf", text_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    assert resp.json()["pages"][0]["source"] == "ocr"
    assert route.call_count == 1


@respx.mock
def test_pages_range(client):
    pdf = make_blank_pdf(3)
    route = _ocr_route()
    resp = client.post(
        "/api/extract",
        data={"pages": "1,3"},
        files={"file": ("multi.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    pages = resp.json()["pages"]
    assert [p["page"] for p in pages] == [1, 3]
    assert route.call_count == 2


@respx.mock
def test_ndjson_order(client, blank_pdf_bytes):
    _ocr_route()
    resp = client.post(
        "/api/extract",
        files={"file": ("scan.pdf", blank_pdf_bytes, "application/pdf")},
        headers={"Accept": "application/x-ndjson"},
    )
    assert resp.status_code == 200
    lines = [json.loads(line) for line in resp.text.strip().splitlines()]
    assert lines[0]["type"] == "page"
    assert lines[-1]["type"] == "done"
    assert lines[-1]["text"] == "OCR markdown text"


@respx.mock
def test_ocr_backend_500(client, png_bytes):
    respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    resp = client.post(
        "/api/extract",
        files={"file": ("page.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pages"][0]["error"]
    assert body["pages"][0]["text"] == ""


@respx.mock
def test_ocr_timeout(client, png_bytes):
    respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(
        side_effect=httpx.ReadTimeout("timeout")
    )
    resp = client.post(
        "/api/extract",
        files={"file": ("page.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["pages"][0]["error"]


def test_reject_wrong_magic(client):
    resp = client.post(
        "/api/extract",
        files={"file": ("fake.pdf", b"not-a-real-file", "application/pdf")},
    )
    assert resp.status_code == 415


def test_reject_oversize(client):
    data = make_png_bytes() + (b"x" * (1024 * 1024))
    resp = client.post(
        "/api/extract",
        files={"file": ("big.png", data, "image/png")},
    )
    assert resp.status_code == 413


def test_too_many_pages(client, monkeypatch):
    pdf = make_blank_pdf(6)
    resp = client.post(
        "/api/extract",
        files={"file": ("many.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "too_many_pages"


@respx.mock
def test_no_extracted_text_in_logs(client, text_pdf_bytes, caplog):
    _ocr_route()
    with caplog.at_level(logging.INFO):
        resp = client.post(
            "/api/extract",
            files={"file": ("doc.pdf", text_pdf_bytes, "application/pdf")},
        )
    assert resp.status_code == 200
    extracted = resp.json()["text"]
    assert extracted
    joined = " ".join(r.message for r in caplog.records)
    assert extracted not in joined
    assert "Hello digital PDF" not in joined

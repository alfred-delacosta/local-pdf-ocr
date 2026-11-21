# Copyright Advanced Software and AI Solutions LLC
"""HTTP client and NDJSON parsing for ocr_mcp."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest
import respx

from ocr_mcp.client import ApiClientError, OcrApiClient, parse_ndjson_lines


def test_parse_pages_then_done():
    lines = [
        json.dumps({"type": "page", "page": 1, "source": "text-layer", "text": "secret page text"}),
        json.dumps(
            {
                "type": "done",
                "text": "full text",
                "pages": [{"page": 1, "source": "text-layer", "text": "secret page text"}],
                "model": "m",
                "durationMs": 12,
                "file": {"name": "a.pdf", "type": "pdf", "pageCount": 1},
            }
        ),
    ]
    result = asyncio.run(parse_ndjson_lines(lines))
    assert result.text == "full text"
    assert result.pages[0].page == 1
    assert result.pages[0].source == "text-layer"
    assert "text" not in result.pages[0].to_public()
    assert result.to_structured()["pages"][0] == {"page": 1, "source": "text-layer"}


def test_parse_done_with_error():
    lines = [
        json.dumps(
            {
                "type": "done",
                "text": "",
                "pages": [],
                "model": "m",
                "durationMs": 0,
                "file": {"name": "a.pdf", "type": "pdf", "pageCount": 0},
                "error": {"code": "too_many_pages", "message": "too many"},
            }
        )
    ]
    with pytest.raises(ApiClientError) as exc:
        asyncio.run(parse_ndjson_lines(lines))
    assert exc.value.code == "too_many_pages"


def test_parse_stream_without_done():
    lines = [json.dumps({"type": "page", "page": 1, "source": "ocr", "text": "x"})]
    with pytest.raises(ApiClientError) as exc:
        asyncio.run(parse_ndjson_lines(lines))
    assert exc.value.code == "bad_stream"


def test_page_errors_kept():
    lines = [
        json.dumps(
            {"type": "page", "page": 2, "source": "ocr", "text": "", "error": "backend timeout"}
        ),
        json.dumps(
            {
                "type": "done",
                "text": "",
                "pages": [],
                "model": "m",
                "durationMs": 3,
                "file": {"name": "a.pdf", "type": "pdf", "pageCount": 2},
            }
        ),
    ]
    result = asyncio.run(parse_ndjson_lines(lines))
    assert result.pages[0].error == "backend timeout"
    assert result.pages[0].to_public()["error"] == "backend timeout"


@respx.mock
def test_busy_retry_then_success():
    settings = respx.get("http://127.0.0.1:3000/api/settings").mock(
        return_value=httpx.Response(
            200,
            json={"defaults": {"maxUploadMb": 50, "lmstudioTimeoutS": 5}},
        )
    )
    extract = respx.post("http://127.0.0.1:3000/api/extract")
    extract.side_effect = [
        httpx.Response(
            503,
            json={"error": {"code": "busy", "message": "Another extraction is in progress."}},
        ),
        httpx.Response(
            200,
            text=json.dumps(
                {
                    "type": "done",
                    "text": "ok",
                    "pages": [],
                    "model": "m",
                    "durationMs": 1,
                    "file": {"name": "a.pdf", "type": "pdf", "pageCount": 1},
                }
            )
            + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        ),
    ]
    client = OcrApiClient("http://127.0.0.1:3000", retries=2)
    result = asyncio.run(client.extract_file(filename="a.pdf", data=b"%PDF"))
    assert result.text == "ok"
    assert settings.called
    assert extract.call_count == 2


@respx.mock
def test_busy_retry_exhausted():
    respx.get("http://127.0.0.1:3000/api/settings").mock(
        return_value=httpx.Response(
            200,
            json={"defaults": {"maxUploadMb": 50, "lmstudioTimeoutS": 5}},
        )
    )
    respx.post("http://127.0.0.1:3000/api/extract").mock(
        return_value=httpx.Response(
            503,
            json={"error": {"code": "busy", "message": "busy"}},
        )
    )
    client = OcrApiClient("http://127.0.0.1:3000", retries=1)
    with pytest.raises(ApiClientError) as exc:
        asyncio.run(client.extract_file(filename="a.pdf", data=b"%PDF"))
    assert exc.value.code == "busy"
    assert "OCR is busy" in exc.value.message


@respx.mock
def test_connection_refused_message():
    respx.get("http://127.0.0.1:3000/api/health").mock(side_effect=httpx.ConnectError("refused"))
    client = OcrApiClient("http://127.0.0.1:3000")
    with pytest.raises(ApiClientError) as exc:
        asyncio.run(client.get_health())
    assert "API not running" in exc.value.message


@respx.mock
def test_timeout_message():
    respx.get("http://127.0.0.1:3000/api/health").mock(side_effect=httpx.ReadTimeout("slow"))
    client = OcrApiClient("http://127.0.0.1:3000")
    with pytest.raises(ApiClientError) as exc:
        asyncio.run(client.get_health())
    assert exc.value.code == "timeout"


@respx.mock
def test_forbidden_host_message():
    respx.get("http://127.0.0.1:3000/api/health").mock(
        return_value=httpx.Response(
            403,
            json={
                "error": {
                    "code": "forbidden_host",
                    "message": "Request Host header is not allowed.",
                }
            },
        )
    )
    client = OcrApiClient("http://127.0.0.1:3000")
    with pytest.raises(ApiClientError) as exc:
        asyncio.run(client.get_health())
    assert exc.value.code == "forbidden_host"
    assert "127.0.0.1" in exc.value.message


@respx.mock
def test_no_origin_header_sent():
    route = respx.get("http://127.0.0.1:3000/api/health").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "backend": {"url": "x", "reachable": True, "latencyMs": 1},
                "model": {"id": "m", "available": True},
            },
        )
    )
    client = OcrApiClient("http://127.0.0.1:3000")
    asyncio.run(client.get_health())
    assert route.called
    headers = route.calls[0].request.headers
    assert "origin" not in headers


@respx.mock
def test_logs_omit_extracted_text(caplog):
    respx.get("http://127.0.0.1:3000/api/settings").mock(
        return_value=httpx.Response(
            200,
            json={"defaults": {"maxUploadMb": 50, "lmstudioTimeoutS": 5}},
        )
    )
    secret = "UNIQUE_SECRET_EXTRACTED_TEXT_XYZ"
    body = (
        json.dumps({"type": "page", "page": 1, "source": "ocr", "text": secret})
        + "\n"
        + json.dumps(
            {
                "type": "done",
                "text": secret,
                "pages": [],
                "model": "m",
                "durationMs": 9,
                "file": {"name": "a.pdf", "type": "pdf", "pageCount": 1},
            }
        )
        + "\n"
    )
    respx.post("http://127.0.0.1:3000/api/extract").mock(
        return_value=httpx.Response(
            200,
            text=body,
            headers={"Content-Type": "application/x-ndjson"},
        )
    )
    client = OcrApiClient("http://127.0.0.1:3000", retries=0)
    with caplog.at_level(logging.INFO):
        result = asyncio.run(client.extract_file(filename="a.pdf", data=b"%PDF-secret-bytes"))
    assert result.text == secret
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert secret not in joined
    assert "%PDF-secret-bytes" not in joined

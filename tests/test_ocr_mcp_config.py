# Copyright Advanced Software and AI Solutions LLC
"""URL building for the MCP API client."""

from __future__ import annotations

import pytest

from ocr_mcp.config import ConfigError, build_api_url, validate_api_url


def test_ocr_api_url_wins(monkeypatch):
    monkeypatch.setenv("OCR_API_URL", "http://127.0.0.1:4000")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "3000")
    assert build_api_url(load_env_file=False) == "http://127.0.0.1:4000"


def test_host_port_zero_maps_to_loopback(monkeypatch):
    monkeypatch.delenv("OCR_API_URL", raising=False)
    assert (
        build_api_url(host="0.0.0.0", port="3000", ocr_api_url="", load_env_file=False)
        == "http://127.0.0.1:3000"
    )


def test_empty_host_maps_to_loopback(monkeypatch):
    monkeypatch.delenv("OCR_API_URL", raising=False)
    assert (
        build_api_url(host="", port=3000, ocr_api_url="", load_env_file=False)
        == "http://127.0.0.1:3000"
    )


def test_ipv6_any_maps_to_loopback(monkeypatch):
    monkeypatch.delenv("OCR_API_URL", raising=False)
    assert (
        build_api_url(host="::", port=3000, ocr_api_url="", load_env_file=False)
        == "http://127.0.0.1:3000"
    )


def test_default_url(monkeypatch):
    monkeypatch.delenv("OCR_API_URL", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert build_api_url(ocr_api_url="", host=None, port=None, load_env_file=False) == (
        "http://127.0.0.1:3000"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://127.0.0.1:3000",
        "http://user:pass@127.0.0.1:3000",
        "http://127.0.0.1:3000?x=1",
        "http://127.0.0.1:3000/api",
        "not-a-url",
    ],
)
def test_reject_bad_urls(raw):
    with pytest.raises(ConfigError):
        validate_api_url(raw)

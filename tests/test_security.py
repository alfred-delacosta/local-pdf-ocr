# Copyright Advanced Software and AI Solutions LLC

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

import app.config as config_mod
import app.settings_store as settings_mod
from app.main import create_app
from app.security import host_allowed, origin_allowed, public_host_names


def test_foreign_host_rejected(client):
    resp = client.get("/api/health", headers={"Host": "evil.example"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_host"


def test_foreign_origin_rejected(client):
    resp = client.get(
        "/api/health",
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_origin"


def test_security_headers_present(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert "default-src 'self'" in resp.headers.get("content-security-policy", "")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("referrer-policy") == "no-referrer"


def test_bind_any_not_in_public_names():
    names = public_host_names("0.0.0.0", ("ocr.lan",))
    assert "0.0.0.0" not in names
    assert "ocr.lan" in names
    assert "127.0.0.1" in names


def test_host_allowed_with_allowed_hosts():
    assert host_allowed("ocr.lan:3000", "0.0.0.0", 3000, ("ocr.lan",))
    assert not host_allowed("ocr.lan:3000", "0.0.0.0", 3000, ())
    assert not host_allowed("0.0.0.0:3000", "0.0.0.0", 3000, ("ocr.lan",))


def test_origin_allowed_with_allowed_hosts():
    assert origin_allowed("http://ocr.lan:3000", "0.0.0.0", 3000, ("ocr.lan",))
    assert not origin_allowed("http://ocr.lan:3000", "0.0.0.0", 3000, ())


@respx.mock
def test_custom_dns_host_accepted_when_configured(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(config_mod, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(config_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", settings_path)
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "3000")
    monkeypatch.setenv("ALLOWED_HOSTS", "ocr.lan,pdf.home")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("MODEL_ID", "LightOnOCR-3-0.8B")
    respx.get("http://127.0.0.1:1234/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "LightOnOCR-3-0.8B"}]})
    )
    app = create_app()
    with TestClient(app, base_url="http://ocr.lan:3000") as client:
        resp = client.get("/api/health", headers={"Host": "ocr.lan:3000"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        settings = client.get("/api/settings", headers={"Host": "ocr.lan:3000"})
        assert settings.status_code == 200
        assert settings.json()["defaults"]["allowedHosts"] == ["ocr.lan", "pdf.home"]

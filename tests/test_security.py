# Copyright Advanced Software and AI Solutions LLC

from __future__ import annotations


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

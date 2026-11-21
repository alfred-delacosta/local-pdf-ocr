# Copyright Advanced Software and AI Solutions LLC

from __future__ import annotations

import httpx
import respx


@respx.mock
def test_health_up(client):
    respx.get("http://127.0.0.1:1234/v1/models").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "LightOnOCR-3-0.8B"}]},
        )
    )
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["backend"]["reachable"] is True
    assert body["model"]["available"] is True


@respx.mock
def test_health_down(client):
    respx.get("http://127.0.0.1:1234/v1/models").mock(side_effect=httpx.ConnectError("down"))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["backend"]["reachable"] is False


@respx.mock
def test_models_list(client):
    respx.get("http://127.0.0.1:1234/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})
    )
    resp = client.get("/api/models")
    assert resp.status_code == 200
    assert resp.json()["models"] == ["a", "b"]


def test_settings_get_and_put_and_reset(client, tmp_path):
    got = client.get("/api/settings")
    assert got.status_code == 200
    assert got.json()["lmstudioBaseUrl"] == "http://127.0.0.1:1234/v1"

    bad = client.put(
        "/api/settings",
        content='{"lmstudioBaseUrl":"http://127.0.0.1:9999/v1","modelId":"x"}',
        headers={"Content-Type": "text/plain"},
    )
    assert bad.status_code == 415

    saved = client.put(
        "/api/settings",
        json={
            "lmstudioBaseUrl": "http://127.0.0.1:9999/v1",
            "modelId": "other-model",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["modelId"] == "other-model"

    again = client.get("/api/settings")
    assert again.json()["lmstudioBaseUrl"] == "http://127.0.0.1:9999/v1"

    reset = client.delete("/api/settings")
    assert reset.status_code == 200
    assert reset.json()["lmstudioBaseUrl"] == "http://127.0.0.1:1234/v1"


def test_settings_reject_bad_urls(client):
    cases = [
        "ftp://127.0.0.1:1234/v1",
        "http://user:pass@127.0.0.1:1234/v1",
        "javascript:alert(1)",
        "http://127.0.0.1:1234/v1?x=1",
    ]
    for url in cases:
        resp = client.put(
            "/api/settings",
            json={"lmstudioBaseUrl": url, "modelId": "m"},
        )
        assert resp.status_code == 422, url
        assert resp.json()["error"]["code"] == "invalid_url"

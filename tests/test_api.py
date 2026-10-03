from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harbinger.api import create_app
from harbinger.config import Config
from harbinger.state import StateStore

REPO = Path(__file__).resolve().parent.parent
TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path):
    cfg = Config(agent_token=TOKEN, snapshot=tmp_path / "state.json", web_dir=REPO / "web")
    return TestClient(create_app(cfg, StateStore(cfg.snapshot)))


def test_state_starts_empty(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    assert r.json()["slots"] == {}
    assert r.headers["cache-control"] == "no-store"


def test_put_requires_token(client):
    r = client.put("/api/slots/notices", json={"text": "x"})
    assert r.status_code == 401
    r = client.put("/api/slots/notices", json={"text": "x"}, headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 403


def test_put_unknown_or_unwritable_slot(client):
    assert client.put("/api/slots/calendar", json={}, headers=AUTH).status_code == 404
    assert client.put("/api/slots/weather", json={}, headers=AUTH).status_code == 404


def test_put_invalid_body(client):
    r = client.put("/api/slots/news", json={"items": [{"title": "no summary"}]}, headers=AUTH)
    assert r.status_code == 400
    assert "summary" in r.json()["detail"]
    r = client.put("/api/slots/news", content=b"not json", headers={**AUTH, "Content-Type": "application/json"})
    assert r.status_code == 400


def test_put_then_get(client):
    body = {"headline": "Server is up", "text": "**Homelab**\nall green"}
    r = client.put("/api/slots/notices", json=body, headers=AUTH)
    assert r.status_code == 204
    slot = client.get("/api/state").json()["slots"]["notices"]
    assert slot["headline"] == "Server is up"
    assert "updated_at" in slot
    health = client.get("/api/health").json()
    assert health["ok"] and health["slots"]["notices"] is not None and health["slots"]["weather"] is None


def test_put_refused_without_configured_token(tmp_path):
    cfg = Config(agent_token=None, snapshot=tmp_path / "state.json", web_dir=REPO / "web")
    c = TestClient(create_app(cfg, StateStore(cfg.snapshot)))
    assert c.put("/api/slots/notices", json={"text": "x"}, headers=AUTH).status_code == 403


def test_serves_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>Harbinger</title>" in r.text
    assert client.get("/config.js").status_code == 200

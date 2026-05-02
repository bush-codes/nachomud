"""Tests for the WebSocket server: /health, /, /ws session flow."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import nachomud.auth.accounts as accounts_mod
import nachomud.auth.magic_link as auth
import nachomud.characters.save as player_mod
from nachomud.server import app


def _make_authed_client(tmp_path, monkeypatch, email="test@example.com"):
    """A TestClient pre-logged-in with a session cookie. Disables the
    agent runner and points all data dirs at the test tmp path."""
    import nachomud.world.store as world_store
    monkeypatch.setenv("NACHOMUD_DISABLE_AGENTS", "1")
    monkeypatch.setattr(player_mod, "DATA_ROOT", str(tmp_path / "players"))
    monkeypatch.setattr(world_store, "DATA_ROOT", str(tmp_path / "world"))
    monkeypatch.setattr(accounts_mod, "DATA_ROOT", str(tmp_path / "accounts"))
    c = TestClient(app)
    cookie = auth.make_session_cookie(email)
    c.cookies.set(auth.SESSION_COOKIE_NAME, cookie)
    return c


@pytest.fixture
def client(tmp_path, monkeypatch):
    return _make_authed_client(tmp_path, monkeypatch)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_serves_terminal(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "NachoMUD" in body
    assert "xterm" in body.lower()


def test_static_client_js(client):
    r = client.get("/static/client.js")
    assert r.status_code == 200
    assert "WebSocket" in r.text


def _read_msg(ws):
    return json.loads(ws.receive_text())


def _drain(ws, max_msgs=20):
    out = []
    for _ in range(max_msgs):
        msg = _read_msg(ws)
        out.append(msg)
        if msg.get("type") == "prompt":
            return out
    return out


def test_ws_welcome_no_saves_offers_new(client):
    with client.websocket_connect("/ws") as ws:
        msgs = _drain(ws)
        text = "".join(m["text"] for m in msgs if m["type"] == "output")
        assert "⚔" in text
        # Logged-in user with no character → anon-flow welcome
        assert "create your character" in text.lower()
        assert any(m.get("type") == "mode" for m in msgs)


def test_ws_welcome_with_saves_lists_them(tmp_path, monkeypatch):
    c = _make_authed_client(tmp_path, monkeypatch, email="aric@example.com")
    from nachomud.characters.character import create_character
    from nachomud.rules.stats import Stats
    p = create_character("Aric", "Dwarf", "Warrior",
                         Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13),
                         player_id="seeded-1")
    player_mod.save_player(p)
    acct = accounts_mod.create_account("aric@example.com")
    accounts_mod.link_player(acct, "seeded-1")

    with c.websocket_connect("/ws") as ws:
        msgs = _drain(ws)
        text = "".join(m["text"] for m in msgs if m["type"] == "output")
        assert "Aric" in text
        assert "Dwarf" in text
        assert "Warrior" in text


def test_ws_handles_malformed_json(client):
    with client.websocket_connect("/ws") as ws:
        _drain(ws)
        ws.send_text("{not json")
        msg = _read_msg(ws)
        assert msg["type"] == "output"
        assert "malformed" in msg["text"].lower()


# ── Public-surface lockdown ──

def test_actors_endpoint_removed(client):
    """GET /actors used to leak full actor state. Sidebar gets the
    same data via WS now; the public endpoint is gone."""
    assert client.get("/actors").status_code == 404


def test_map_endpoint_returns_ascii(client):
    """GET /map returns a JSON payload with an ASCII rendering of the
    union of all actors' explored rooms. Anchored at silverbrook.inn
    so the renderer always has a placeable current_room_id."""
    r = client.get("/map")
    assert r.status_code == 200
    data = r.json()
    assert "map" in data
    # Anchor room name should appear when the world is seeded.
    body = data["map"]
    assert isinstance(body, str)
    assert len(body) > 0


def test_openapi_off_in_prod_mode(monkeypatch):
    """Without NACHOMUD_DEV_DOCS, FastAPI's auto-docs must 404."""
    # The fixture client uses the module-level `app`, which captured the
    # env at import. Build a fresh app here with the prod default.
    monkeypatch.delenv("NACHOMUD_DEV_DOCS", raising=False)
    import importlib
    import nachomud.server as server_mod
    importlib.reload(server_mod)
    c = TestClient(server_mod.app)
    assert c.get("/docs").status_code == 404
    assert c.get("/redoc").status_code == 404
    assert c.get("/openapi.json").status_code == 404


def test_openapi_on_when_dev_docs_enabled(monkeypatch):
    """NACHOMUD_DEV_DOCS=1 re-enables the auto-docs for local dev."""
    monkeypatch.setenv("NACHOMUD_DEV_DOCS", "1")
    import importlib
    import nachomud.server as server_mod
    importlib.reload(server_mod)
    c = TestClient(server_mod.app)
    assert c.get("/openapi.json").status_code == 200
    assert c.get("/docs").status_code == 200


def test_auth_request_whitelist_blocks_non_listed(client, monkeypatch):
    """When NACHOMUD_AUTH_ALLOWED_EMAILS is set, only listed addresses
    actually get magic links — but the response is identical so the
    allowlist isn't enumerable."""
    monkeypatch.setenv("NACHOMUD_AUTH_ALLOWED_EMAILS", "ok@example.com")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(auth, "send_magic_link",
                        lambda email, link: sent.append((email, link)))
    # Non-listed email: response is ok but no email sent.
    r1 = client.post("/auth/request", json={"email": "evil@example.com"})
    assert r1.status_code == 200
    assert r1.json() == {"ok": True}
    assert sent == []
    # Listed email: response is ok and email IS sent.
    r2 = client.post("/auth/request", json={"email": "ok@example.com"})
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}
    assert len(sent) == 1
    assert sent[0][0] == "ok@example.com"


def test_auth_request_no_whitelist_is_wide_open(client, monkeypatch):
    """Without the env var, behavior is unchanged: any email gets
    a magic link sent (privacy: leaks nothing about accounts)."""
    monkeypatch.delenv("NACHOMUD_AUTH_ALLOWED_EMAILS", raising=False)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(auth, "send_magic_link",
                        lambda email, link: sent.append((email, link)))
    r = client.post("/auth/request", json={"email": "anyone@example.com"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert len(sent) == 1

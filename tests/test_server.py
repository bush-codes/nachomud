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

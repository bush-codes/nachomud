"""FastAPI WebSocket backend for NachoMUD.

Each WS connection is a *viewer* — it watches one actor at a time
(their own player, or one of the 4 AI agents). The WorldLoop broadcasts
each actor's outgoing messages to every subscriber of that actor; the
per-WS forwarder task drains them onto the socket.

Message protocol:
  client → server:
    {"type": "command",   "text": "look"}
    {"type": "subscribe", "actor_id": "agent_scholar"}

  server → client:
    {"type": "actor_list", "actors": [...]}
    {"type": "you",        "actor_id": "human_<pid>"}
    {"type": "subscribed", "actor_id": "..."}
    {"type": "output",     "text": "...", "actor_id": "...", "ansi": true}
    {"type": "prompt",     "text": "...", "actor_id": "..."}
    {"type": "mode",       "mode": "...", "actor_id": "..."}
    {"type": "status",     "hp": ..., "actor_id": "..."}
    {"type": "thinking",   "text": "...", "actor_id": "..."}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

import nachomud.auth.accounts as accounts_mod
import nachomud.auth.magic_link as auth
from nachomud.engine.session import Session
from nachomud.style import RED, YELLOW, _c
from nachomud.world.directions import is_direction
from nachomud.world.loop import WorldLoop, set_world_loop


log = logging.getLogger("nachomud.server")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot the shared WorldLoop on startup, tear it down on shutdown.

    NACHOMUD_DISABLE_AGENTS=1 (set by tests) skips spawning the 4
    LLM-driven agent runners — they'd otherwise hang waiting on Ollama
    when the box isn't running it locally."""
    enable_agents = not bool(os.environ.get("NACHOMUD_DISABLE_AGENTS", ""))
    loop = WorldLoop(enable_agent_runner=enable_agents)
    await loop.start()
    set_world_loop(loop)
    app.state.world_loop = loop
    try:
        yield
    finally:
        await loop.stop()


# OpenAPI / Swagger / ReDoc are auto-exposed by FastAPI by default. In
# production they leak the route map; only enable when explicitly opted
# in (NACHOMUD_DEV_DOCS=1) so they're available locally during dev but
# closed publicly. The static spec checked in at docs/openapi.json
# stays the canonical reference.
_DEV_DOCS = bool(os.environ.get("NACHOMUD_DEV_DOCS", ""))
app = FastAPI(
    title="NachoMUD",
    lifespan=lifespan,
    docs_url="/docs" if _DEV_DOCS else None,
    redoc_url="/redoc" if _DEV_DOCS else None,
    openapi_url="/openapi.json" if _DEV_DOCS else None,
)

# server.py lives in nachomud/; static frontend lives at <repo>/web/.
TERMINAL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# ── Wire helpers ──

def _msg_to_dict(item) -> dict | None:
    if isinstance(item, dict):
        return item
    if not isinstance(item, tuple) or len(item) < 2:
        return None
    kind, payload = item
    if kind == "output":
        return {"type": "output", "text": payload, "ansi": True}
    if kind == "prompt":
        return {"type": "prompt", "text": payload}
    if kind == "mode":
        return {"type": "mode", "mode": payload}
    if kind == "close":
        return {"type": "close"}
    return None


async def _send(ws: WebSocket, msg: dict) -> None:
    await ws.send_text(json.dumps(msg))


# ── Thinking verbs ──

_DM_VERBS = ["The Dungeon Master gathers their thoughts",
             "The Dungeon Master considers your words",
             "The DM weighs the moment"]
_NPC_VERBS = ["They take a breath before speaking",
              "Words form on their lips",
              "They pause, then turn to you"]
_GEN_VERBS = ["The land takes shape as you step into it",
              "Mist parts ahead of you",
              "Stones and earth settle into place"]
_ADJUDICATE_VERBS = ["The Dungeon Master weighs your intent",
                     "The world holds its breath",
                     "Reality decides what to make of this"]


def _pick_thinking(text: str, session: Session | None) -> str | None:
    if session is None:
        return None
    cmd, _, _ = text.strip().partition(" ")
    cmd = cmd.lower()
    if session.handler_kind in ("welcome", "char_create"):
        return None
    if cmd in ("dm", "ask"):
        return random.choice(_DM_VERBS) + "…"
    if cmd in ("talk", "tell"):
        return random.choice(_NPC_VERBS) + "…"
    if cmd == "go" or is_direction(cmd):
        return random.choice(_GEN_VERBS) + "…"
    if cmd in ("look", "l", "exits", "inventory", "inv", "i", "stats", "who",
               "help", "save", "quit", "exit", "get", "take", "drop", "wait",
               "sleep", "rest", "attack", "flee", "run", "escape", "status",
               "buy", "wares", "shop"):
        return None
    return random.choice(_ADJUDICATE_VERBS) + "…"


# ── Auth-resolved player_id ──

def _resolve_player_id(ws: WebSocket) -> tuple[str, str | None]:
    """Decide which player_id to bind this WS to. Authenticated → resolve
    from the account. Anon → no Session, pure spectator."""
    cookie_value = ws.cookies.get(auth.SESSION_COOKIE_NAME, "")
    email = auth.read_session_cookie(cookie_value) if cookie_value else None
    if email is None:
        return "", None
    account = accounts_mod.find_account_by_email(email) or accounts_mod.create_account(email)
    if account.player_ids:
        return accounts_mod.primary_player_id(account), account.email
    new_pid = f"acct-{uuid.uuid4()}"
    accounts_mod.link_player(account, new_pid)
    return new_pid, account.email


# ── Forwarder: drain the per-WS queue onto the socket ──

async def _forwarder(ws: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        item = await queue.get()
        try:
            if isinstance(item, tuple) and item and item[0] == "scoped":
                _, actor_id, msg = item
                d = _msg_to_dict(msg)
                if d is not None:
                    d["actor_id"] = actor_id
                    if d.get("type") == "close":
                        await ws.close()
                        return
                    await _send(ws, d)
            elif isinstance(item, tuple) and item and item[0] == "self":
                _, msg = item
                d = _msg_to_dict(msg)
                if d is not None:
                    if d.get("type") == "close":
                        await ws.close()
                        return
                    await _send(ws, d)
            elif isinstance(item, tuple) and item and item[0] == "event":
                _, payload = item
                if isinstance(payload, dict):
                    await _send(ws, payload)
            elif isinstance(item, dict):
                await _send(ws, item)
        except WebSocketDisconnect:
            return


# ── WS session ──

async def _next_command(ws: WebSocket) -> str | None:
    try:
        return await ws.receive_text()
    except WebSocketDisconnect:
        return None


async def game_session(ws: WebSocket) -> None:
    world_loop: WorldLoop | None = getattr(ws.app.state, "world_loop", None)
    pid, account_email = _resolve_player_id(ws)
    # Anon viewers (no cookie) → no Session, spectator only.
    session = Session(world_loop=world_loop, anon_player_id=pid) if account_email else None

    queue: asyncio.Queue = asyncio.Queue()
    sub = world_loop.add_subscriber(queue) if world_loop is not None else None
    forwarder = asyncio.create_task(_forwarder(ws, queue))

    if world_loop is not None:
        await queue.put(("event", world_loop.actor_list_event()))

    async def push_self(item) -> None:
        await queue.put(("self", item))
        if sub is not None:
            sub.self_transcript.append(item)

    if session is not None:
        for m in session.start():
            await push_self(m)

    try:
        while True:
            raw = await _next_command(ws)
            if raw is None:
                log.info("client disconnected")
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(ws, {"type": "output",
                                  "text": _c(f"[malformed json] {raw}\r\n", RED),
                                  "ansi": True})
                continue
            msg_type = msg.get("type")
            text = msg.get("text", "") if msg_type == "command" else ""

            if msg_type == "subscribe":
                actor_id = (msg.get("actor_id") or "").strip()
                if world_loop is None or sub is None:
                    continue
                ok = world_loop.set_subscription(sub, actor_id)
                if not ok:
                    await _send(ws, {"type": "output",
                                      "text": _c(f"[unknown actor: {actor_id}]\r\n", YELLOW),
                                      "ansi": True})
                continue

            if msg_type != "command":
                await _send(ws, {"type": "output",
                                  "text": _c(f"[unknown msg type] {msg_type}\r\n", YELLOW),
                                  "ansi": True})
                continue

            if session is None:
                await _send(ws, {"type": "output",
                                  "text": _c(
                                      "(Sign in by email to play your own character.)\r\n",
                                      YELLOW),
                                  "ansi": True})
                continue

            # Reject commands aimed at agents — only your own actor accepts input.
            if (sub is not None and sub.actor_id and session.actor_id
                    and sub.actor_id != session.actor_id):
                await _send(ws, {"type": "output",
                                  "text": _c(
                                      "(You're spectating an agent — switch to "
                                      "'My Player' to send commands.)\r\n", YELLOW),
                                  "ansi": True,
                                  "actor_id": sub.actor_id})
                continue

            verb = _pick_thinking(text, session)
            if verb:
                await queue.put(("event",
                                 {"type": "thinking", "text": verb,
                                  "actor_id": session.actor_id or ""}))
            try:
                msgs = await asyncio.to_thread(session.handle, text)
            except Exception:
                log.exception("session.handle raised")
                await _send(ws, {"type": "output",
                                  "text": _c("\r\n[server error — see logs]\r\n", RED),
                                  "ansi": True})
                if verb:
                    await queue.put(("event", {"type": "thinking", "text": ""}))
                continue
            if verb:
                await queue.put(("event", {"type": "thinking", "text": "",
                                            "actor_id": session.actor_id or ""}))

            # In-game with world_loop: msgs already broadcast by submit_command.
            # Pre-actor: push to self queue.
            if (world_loop is None
                    or session.handler_kind != "in_game"
                    or not session.actor_id):
                for m in msgs:
                    await push_self(m)

            # First time entering in_game: auto-subscribe + tell client which
            # actor is "you" so the sidebar labels its My-Player slot.
            if (world_loop is not None and sub is not None
                    and session.actor_id and not sub.actor_id):
                world_loop.set_subscription(sub, session.actor_id)
                await queue.put(("event",
                                 {"type": "you", "actor_id": session.actor_id}))
    finally:
        forwarder.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await forwarder
        if world_loop is not None and sub is not None:
            world_loop.remove_subscriber(sub)
        if world_loop is not None and session is not None and session.actor_id:
            world_loop.unregister_human(session.actor_id)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    log.info("client connected")
    await game_session(ws)


# ── HTTP routes ──

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── Auth routes ──

def _looks_like_email(s: str) -> bool:
    if not s or len(s) > 254 or " " in s:
        return False
    local, _, domain = s.rpartition("@")
    return bool(local and domain and "." in domain)


def _allowed_emails() -> set[str] | None:
    """Whitelist for /auth/request. None means wide open. A set means
    only those (lowercased) addresses get magic links — others receive
    the same {ok: true} but no email is sent (don't leak which
    addresses are on the list)."""
    raw = os.environ.get("NACHOMUD_AUTH_ALLOWED_EMAILS", "").strip()
    if not raw:
        return None
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


@app.post("/auth/request")
async def auth_request(request: Request) -> JSONResponse:
    """Generate a magic-link token and email it. Always responds {ok: true}
    regardless of whether the email is known or whitelisted — leaks
    nothing about which addresses are accepted."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = (body.get("email") or "").strip().lower()
    if not _looks_like_email(email):
        return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)
    allowed = _allowed_emails()
    if allowed is not None and email not in allowed:
        # Same response shape as success — caller can't distinguish
        # "not on allowlist" from "valid request, link sent."
        log.info("auth_request: rejected non-allowlisted email")
        return JSONResponse({"ok": True})
    token = auth.issue_token(email)
    base = str(request.base_url).rstrip("/")
    link = f"{base}/auth/verify?token={token}"
    try:
        auth.send_magic_link(email, link)
    except Exception:
        log.exception("send_magic_link failed for %s", email)
    return JSONResponse({"ok": True})


@app.get("/auth/verify")
def auth_verify(token: str = "") -> Response:
    email = auth.consume_token(token)
    if email is None:
        return RedirectResponse(url="/?auth=invalid", status_code=303)
    accounts_mod.create_account(email)
    cookie_value = auth.make_session_cookie(email)
    response = RedirectResponse(url="/?auth=ok", status_code=303)
    response.set_cookie(
        key=auth.SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=bool(os.environ.get("NACHOMUD_SECURE_COOKIE", "")),
    )
    return response


@app.post("/auth/logout")
def auth_logout() -> Response:
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return response


@app.get("/auth/me")
def auth_me(request: Request) -> JSONResponse:
    cookie_value = request.cookies.get(auth.SESSION_COOKIE_NAME, "")
    email = auth.read_session_cookie(cookie_value) if cookie_value else None
    body = {"logged_in": False}
    if email is not None:
        account = accounts_mod.find_account_by_email(email)
        body = {
            "logged_in": True,
            "email": email,
            "player_ids": list(account.player_ids) if account else [],
        }
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


# ── Privacy / Terms (rendered from repo root markdown files) ──

def _render_markdown_page(md_path: str, title: str) -> Response:
    try:
        with open(md_path) as f:
            body = f.read()
    except FileNotFoundError:
        return Response(status_code=404, content="Not found")
    import html as _html
    escaped = _html.escape(body)
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><title>{_html.escape(title)} — NachoMUD</title>
<style>
  body {{ background: #0a0a0a; color: #d8d8d8; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; max-width: 720px; margin: 24px auto; padding: 0 16px; }}
  pre {{ white-space: pre-wrap; word-wrap: break-word; line-height: 1.55; font-size: 13px; }}
  a {{ color: #5dd; }}
  .nav {{ font-size: 12px; color: #888; margin-bottom: 16px; }}
</style></head><body>
<div class="nav"><a href="/">← Back to NachoMUD</a></div>
<pre>{escaped}</pre>
</body></html>
"""
    return Response(content=page, media_type="text/html")


@app.get("/privacy")
def privacy() -> Response:
    return _render_markdown_page(os.path.join(_REPO_ROOT, "PRIVACY.md"), "Privacy")


@app.get("/terms")
def terms() -> Response:
    return _render_markdown_page(os.path.join(_REPO_ROOT, "TERMS.md"), "Terms")


# ── Index + static ──

@app.get("/")
def index():
    # Cache-Control: no-store so /?auth=ok always re-runs the JS auth check.
    return FileResponse(
        os.path.join(TERMINAL_DIR, "index.html"),
        headers={"Cache-Control": "no-store"},
    )


if os.path.isdir(TERMINAL_DIR):
    app.mount("/static", StaticFiles(directory=TERMINAL_DIR), name="static")

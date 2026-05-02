from __future__ import annotations

from nachomud.settings import AGENT_OLLAMA_URL, OLLAMA_HTTP_TIMEOUT_SECONDS

# One Ollama client per host URL. The DM tier resolves a per-actor host
# (each player's tailnet-shared Ollama), so over a session the app talks
# to N hosts; we cache so we don't re-allocate the underlying httpx pool
# on every chat() call.
_clients: dict[str, object] = {}


class LLMUnavailable(Exception):
    """The LLM backend is not reachable right now (network error, host
    down, timeout, etc.). Callers should catch this and degrade
    gracefully — the site still serves; agents skip ticks; commands
    that need the LLM return a "not right now" message.

    Distinct from generic Exception so callers can tell "Ollama is
    asleep" apart from "we got malformed output from a working LLM."
    """


def _get_client(host: str):
    client = _clients.get(host)
    if client is None:
        import ollama
        client = ollama.Client(host=host, timeout=OLLAMA_HTTP_TIMEOUT_SECONDS)
        _clients[host] = client
    return client


def chat(*, system: str, message: str, model: str,
         host: str | None = None, max_tokens: int = 200) -> str:
    """Send a chat completion to Ollama and return the text response.

    `host` defaults to AGENT_OLLAMA_URL (the operator's tailnet-shared
    Ollama). The DM tier passes the player's per-actor URL to route the
    expensive smart-model call to that player's GPU.

    Raises LLMUnavailable if the backend can't be reached (host down,
    socket timeout, refused connection). Each player's box can be
    stopped independently of the app box — this is the wire we hit
    when one of those GPUs is off."""
    import httpx
    target = host or AGENT_OLLAMA_URL
    # keep_alive="24h" pins the model in RAM across requests. Without
    # this the Python ollama client sends a short default and Ollama
    # unloads after a few minutes — meaning every other call pays a
    # 100+ second model-load tax on CPU-only hosts.
    try:
        response = _get_client(target).chat(
            model=model,
            keep_alive="24h",
            options={"num_predict": max_tokens},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
            httpx.RemoteProtocolError, ConnectionError) as e:
        raise LLMUnavailable(f"ollama unreachable at {target}: {e}") from e
    return response["message"]["content"].strip()

from __future__ import annotations

import anthropic

from nachomud.settings import (
    ANTHROPIC_API_KEY,
    LLM_BACKEND,
    OLLAMA_BASE_URL,
    OLLAMA_HTTP_TIMEOUT_SECONDS,
)

_anthropic_client: anthropic.Anthropic | None = None
_ollama_client = None

if LLM_BACKEND != "ollama":
    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


class LLMUnavailable(Exception):
    """The LLM backend is not reachable right now (network error, host
    down, timeout, etc.). Callers should catch this and degrade
    gracefully — the site still serves; agents skip ticks; commands
    that need the LLM return a "not right now" message.

    Distinct from generic Exception so callers can tell "Ollama is
    asleep" apart from "we got malformed output from a working LLM."
    """


def _get_ollama_client():
    """Return a cached Ollama client, creating it on first use."""
    global _ollama_client
    if _ollama_client is None:
        import ollama
        _ollama_client = ollama.Client(
            host=OLLAMA_BASE_URL,
            timeout=OLLAMA_HTTP_TIMEOUT_SECONDS,
        )
    return _ollama_client


def chat(*, system: str, message: str, model: str, max_tokens: int = 200) -> str:
    """Send a chat completion and return the text response.

    Raises LLMUnavailable if the backend can't be reached (host down,
    socket timeout, refused connection). The split-architecture deploy
    has the GPU box stoppable independently of the app box — this is
    the wire we hit when the GPU is off."""
    if LLM_BACKEND == "ollama":
        import httpx
        # keep_alive="24h" pins the model in RAM across requests. Without
        # this the Python ollama client sends a short default and Ollama
        # unloads after a few minutes — meaning every other call pays a
        # 100+ second model-load tax on CPU-only hosts.
        try:
            response = _get_ollama_client().chat(
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
            raise LLMUnavailable(f"ollama unreachable: {e}") from e
        return response["message"]["content"].strip()
    response = _anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": message}],
    )
    return response.content[0].text.strip()

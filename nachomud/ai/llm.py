from __future__ import annotations

import anthropic

from nachomud.settings import ANTHROPIC_API_KEY, LLM_BACKEND, OLLAMA_BASE_URL

_anthropic_client: anthropic.Anthropic | None = None
_ollama_client = None

if LLM_BACKEND != "ollama":
    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _get_ollama_client():
    """Return a cached Ollama client, creating it on first use."""
    global _ollama_client
    if _ollama_client is None:
        import ollama
        _ollama_client = ollama.Client(host=OLLAMA_BASE_URL)
    return _ollama_client


def chat(*, system: str, message: str, model: str, max_tokens: int = 200) -> str:
    """Send a chat completion and return the text response."""
    if LLM_BACKEND == "ollama":
        # keep_alive="24h" pins the model in RAM across requests. Without
        # this the Python ollama client sends a short default and Ollama
        # unloads after a few minutes — meaning every other call pays a
        # 100+ second model-load tax on CPU-only hosts.
        response = _get_ollama_client().chat(
            model=model,
            keep_alive="24h",
            options={"num_predict": max_tokens},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
        )
        return response["message"]["content"].strip()
    response = _anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": message}],
    )
    return response.content[0].text.strip()

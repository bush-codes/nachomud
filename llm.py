from __future__ import annotations

import anthropic

from config import ANTHROPIC_API_KEY, LLM_BACKEND, OLLAMA_BASE_URL

_anthropic_client: anthropic.Anthropic | None = None

if LLM_BACKEND != "ollama":
    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def chat(*, system: str, message: str, model: str, max_tokens: int = 200) -> str:
    """Send a chat completion and return the text response."""
    if LLM_BACKEND == "ollama":
        import ollama

        client = ollama.Client(host=OLLAMA_BASE_URL)
        response = client.chat(
            model=model,
            options={"num_predict": max_tokens},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
        )
        return response["message"]["content"].strip()
    else:
        response = _anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        return response.content[0].text.strip()

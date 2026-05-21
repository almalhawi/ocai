from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ocai.prompts import SYSTEM_PROMPT, build_user_message
from ocai.providers.base import Provider, ProviderError, Suggestion

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_HOST = "http://127.0.0.1:11434"


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None):
        self._model = model or os.environ.get("OCAI_OLLAMA_MODEL", DEFAULT_MODEL)
        self._host = (host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)).rstrip("/")

    def suggest(self, request: str, *, context: str | None = None) -> Suggestion:
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(request, context=context)},
            ],
        }
        req = urllib.request.Request(
            f"{self._host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ProviderError(f"could not reach Ollama at {self._host}: {e}") from e
        content = body.get("message", {}).get("content", "")
        if not content:
            raise ProviderError(f"ollama returned no content: {body}")
        return Suggestion.from_json(content)

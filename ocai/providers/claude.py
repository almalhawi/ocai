from __future__ import annotations

import os

from ocai.prompts import SYSTEM_PROMPT, build_user_message
from ocai.providers.base import Provider, ProviderError, Suggestion

DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeProvider(Provider):
    name = "claude"

    def __init__(self, model: str | None = None):
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise ProviderError(
                "anthropic SDK not installed. Run: pip install 'ocai[claude]'"
            ) from e
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        self._client = Anthropic(api_key=api_key)
        self._model = model or os.environ.get("OCAI_CLAUDE_MODEL", DEFAULT_MODEL)

    def suggest(self, request: str, *, context: str | None = None) -> Suggestion:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": build_user_message(request, context=context)}
            ],
        )
        text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        if not text_blocks:
            raise ProviderError("claude returned no text content")
        return Suggestion.from_json(text_blocks[0])

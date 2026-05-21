from __future__ import annotations

import os

from ocai.prompts import SYSTEM_PROMPT, build_user_message
from ocai.providers.base import Provider, ProviderError, Suggestion

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, model: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ProviderError(
                "openai SDK not installed. Run: pip install 'ocai[openai]'"
            ) from e
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        self._client = OpenAI(api_key=api_key)
        self._model = model or os.environ.get("OCAI_OPENAI_MODEL", DEFAULT_MODEL)

    def suggest(self, request: str, *, context: str | None = None) -> Suggestion:
        resp = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(request, context=context)},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            raise ProviderError("openai returned empty content")
        return Suggestion.from_json(content)

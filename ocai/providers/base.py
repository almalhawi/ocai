from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    pass


@dataclass
class Suggestion:
    command: str
    explanation: str
    destructive: bool

    @classmethod
    def from_json(cls, raw: str) -> "Suggestion":
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ProviderError(f"model did not return valid JSON: {e}\n---\n{raw}")
        try:
            return cls(
                command=str(data["command"]).strip(),
                explanation=str(data.get("explanation", "")).strip(),
                destructive=bool(data.get("destructive", True)),
            )
        except KeyError as e:
            raise ProviderError(f"model JSON missing required field: {e}")


class Provider(Protocol):
    name: str

    def suggest(self, request: str) -> Suggestion: ...

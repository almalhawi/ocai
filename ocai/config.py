from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


CONFIG_PATHS = [
    Path.home() / ".config" / "ocai" / "config.toml",
    Path.home() / ".ocai.toml",
]


@dataclass
class Config:
    provider: str = "claude"
    model: str | None = None

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        for path in CONFIG_PATHS:
            if path.is_file() and tomllib is not None:
                with path.open("rb") as f:
                    data = tomllib.load(f)
                if isinstance(data.get("provider"), str):
                    cfg.provider = data["provider"]
                if isinstance(data.get("model"), str):
                    cfg.model = data["model"]
                break
        # env wins over file
        if env_provider := os.environ.get("OCAI_PROVIDER"):
            cfg.provider = env_provider
        if env_model := os.environ.get("OCAI_MODEL"):
            cfg.model = env_model
        return cfg

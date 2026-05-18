from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[import-not-found]
else:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


CONFIG_PATHS = [
    Path.home() / ".config" / "ocai" / "config.toml",
    Path.home() / ".ocai.toml",
]

# Minimal TOML subset for Python <3.11: `key = "value"` or `key = 'value'`,
# one per line, with `#` comments. Sufficient for ocai's flat config.
_KV_RE = re.compile(
    r'^\s*([A-Za-z_][\w-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s#]+))\s*(?:#.*)?$'
)


def _parse_simple_toml(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        m = _KV_RE.match(raw)
        if not m:
            raise ValueError(f"line {lineno}: not a key = \"value\" pair: {raw!r}")
        key = m.group(1)
        value = m.group(2) or m.group(3) or m.group(4) or ""
        out[key] = value
    return out


def _load_file(path: Path) -> dict[str, object]:
    if tomllib is not None:
        with path.open("rb") as f:
            return tomllib.load(f)
    return dict(_parse_simple_toml(path.read_text(encoding="utf-8")))


@dataclass
class Config:
    provider: str = "claude"
    model: str | None = None
    source: str = "defaults"  # "defaults", "<path>", or "env"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        for path in CONFIG_PATHS:
            if not path.is_file():
                continue
            try:
                data = _load_file(path)
            except (ValueError, OSError) as e:
                print(f"ocai: warning: could not read {path}: {e}", file=sys.stderr)
                break
            if isinstance(data.get("provider"), str):
                cfg.provider = data["provider"]  # type: ignore[assignment]
            if isinstance(data.get("model"), str):
                cfg.model = data["model"]  # type: ignore[assignment]
            cfg.source = str(path)
            break
        # env wins over file
        env_used = False
        if env_provider := os.environ.get("OCAI_PROVIDER"):
            cfg.provider = env_provider
            env_used = True
        if env_model := os.environ.get("OCAI_MODEL"):
            cfg.model = env_model
            env_used = True
        if env_used:
            cfg.source = f"{cfg.source} + env" if cfg.source != "defaults" else "env"
        return cfg

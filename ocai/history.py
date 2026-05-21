from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "ocai"


HISTORY_FILE = _state_dir() / "history.jsonl"


def record(entry: dict[str, Any], *, path: Path | None = None) -> None:
    """Append a JSONL record to the history file. Best-effort — disk errors
    don't fail the user's command. Adds a UTC ISO timestamp to every entry."""
    target = path or HISTORY_FILE
    payload = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass

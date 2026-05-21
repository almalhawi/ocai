from __future__ import annotations

import subprocess


def _run(cmd: list[str], timeout: float = 2.0) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def gather() -> str | None:
    """Return a short summary of the current `oc` context, or None if oc isn't
    installed or the user isn't logged in. Best-effort; never raises. We send
    this to the model so it knows the current project/user without us having
    to bake them into the user's prompt."""
    user = _run(["oc", "whoami"])
    project = _run(["oc", "project", "-q"])
    server = _run(["oc", "whoami", "--show-server"])
    if not user and not project:
        return None
    parts = []
    if user:
        parts.append(f"current user: {user}")
    if project:
        parts.append(f"current project (namespace): {project}")
    if server:
        parts.append(f"cluster api: {server}")
    return "\n".join(parts)

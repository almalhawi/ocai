"""Interactive setup wizard. Invoked via `ocai configure`."""

from __future__ import annotations

import getpass
import importlib
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "ocai"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def _bold(s: str) -> str: return _c(s, "1")
def _dim(s: str) -> str: return _c(s, "2")
def _green(s: str) -> str: return _c(s, "32")
def _yellow(s: str) -> str: return _c(s, "33")
def _red(s: str) -> str: return _c(s, "31")
def _cyan(s: str) -> str: return _c(s, "36")


def _ok(msg: str) -> None: print(f"{_green('✓')} {msg}")
def _warn(msg: str) -> None: print(f"{_yellow('!')} {msg}")
def _fail(msg: str) -> None: print(f"{_red('✗')} {msg}")


def _ask(prompt: str, default: str | None = None, *, hidden: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    reader = getpass.getpass if hidden else input
    while True:
        try:
            value = reader(f"{prompt}{suffix}: ").strip()
        except EOFError:
            print()
            raise KeyboardInterrupt
        if value:
            return value
        if default is not None:
            return default


def _ask_yes(prompt: str, *, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    try:
        answer = input(f"{prompt} [{suffix}]: ").strip().lower()
    except EOFError:
        print()
        raise KeyboardInterrupt
    if not answer:
        return default
    return answer in ("y", "yes")


def _check_oc() -> None:
    if shutil.which("oc"):
        _ok("oc is on $PATH")
    else:
        _warn(
            "oc was not found on $PATH. ocai needs it to run any command. "
            "Install from your OpenShift cluster's downloads page or "
            "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/"
        )


def _check_sdk(import_name: str, extra: str) -> bool:
    try:
        importlib.import_module(import_name)
        _ok(f"{import_name} SDK is installed")
        return True
    except ImportError:
        _fail(f"{import_name} SDK is not installed. Install with:")
        print(f"    {_cyan(f'pip install ocai[{extra}]')}")
        print(f"  (or, from a clone: {_cyan(f'pip install -e .[{extra}]')})")
        return False


def _shell_rc_path() -> Path | None:
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return Path.home() / ".zshrc"
    if "bash" in shell:
        return Path.home() / ".bashrc"
    return None


def _offer_persist_env(key: str, value: str) -> None:
    rc = _shell_rc_path()
    export_line = f"export {key}={shlex.quote(value)}"
    print()
    print(f"To persist {_bold(key)} across shells, add to your shell rc:")
    print(f"    {_cyan(export_line)}")
    if rc is None:
        return
    if not _ask_yes(f"Append to {rc}?", default=False):
        return
    marker = f"# Added by `ocai configure`"
    try:
        existing = rc.read_text(encoding="utf-8") if rc.exists() else ""
    except OSError as e:
        _warn(f"could not read {rc}: {e}")
        return
    if f"export {key}=" in existing:
        _warn(f"{rc} already exports {key}; not appending.")
        return
    try:
        with rc.open("a", encoding="utf-8") as f:
            f.write(f"\n{marker}\n{export_line}\n")
    except OSError as e:
        _fail(f"could not write {rc}: {e}")
        return
    _ok(f"appended to {rc}. Reload with: {_cyan(f'source {rc}')}")
    # Also export for any smoke test we run in this process.
    os.environ[key] = value


def _existing_env(key: str) -> str | None:
    value = os.environ.get(key)
    if not value:
        return None
    masked = (value[:7] + "…" + value[-4:]) if len(value) > 14 else "…"
    print(f"{_green('✓')} {key} is already set in this shell ({masked})")
    return value


def _configure_claude() -> dict:
    print()
    print(_bold("Claude (Anthropic)"))
    have_sdk = _check_sdk("anthropic", "claude")
    existing = _existing_env("ANTHROPIC_API_KEY")
    if existing and _ask_yes("Use the existing key?", default=True):
        key = existing
    else:
        key = _ask("ANTHROPIC_API_KEY (input hidden)", hidden=True)
    model = _ask("Model", default="claude-sonnet-4-6")
    if key != existing:
        _offer_persist_env("ANTHROPIC_API_KEY", key)
    os.environ["ANTHROPIC_API_KEY"] = key
    if model != "claude-sonnet-4-6":
        os.environ["OCAI_CLAUDE_MODEL"] = model
    return {"provider": "claude", "model": model, "smoke_ok": have_sdk}


def _configure_openai() -> dict:
    print()
    print(_bold("OpenAI"))
    have_sdk = _check_sdk("openai", "openai")
    existing = _existing_env("OPENAI_API_KEY")
    if existing and _ask_yes("Use the existing key?", default=True):
        key = existing
    else:
        key = _ask("OPENAI_API_KEY (input hidden)", hidden=True)
    model = _ask("Model", default="gpt-4o-mini")
    if key != existing:
        _offer_persist_env("OPENAI_API_KEY", key)
    os.environ["OPENAI_API_KEY"] = key
    if model != "gpt-4o-mini":
        os.environ["OCAI_OPENAI_MODEL"] = model
    return {"provider": "openai", "model": model, "smoke_ok": have_sdk}


def _check_ollama(host: str) -> bool:
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _configure_ollama() -> dict:
    print()
    print(_bold("Ollama (local)"))
    host = _ask("Ollama host", default="http://127.0.0.1:11434").rstrip("/")
    reachable = _check_ollama(host)
    if reachable:
        _ok(f"Ollama daemon reachable at {host}")
    else:
        _warn(f"could not reach Ollama at {host}. Start it with: {_cyan('ollama serve')}")
    model = _ask("Model", default="qwen2.5-coder:7b")
    if reachable and shutil.which("ollama") and _ask_yes(f"Pull '{model}' now?", default=False):
        rc = subprocess.run(["ollama", "pull", model]).returncode
        if rc != 0:
            _warn(f"ollama pull exited {rc}")
    if host != "http://127.0.0.1:11434":
        _offer_persist_env("OLLAMA_HOST", host)
        os.environ["OLLAMA_HOST"] = host
    return {"provider": "ollama", "model": model, "smoke_ok": reachable}


def _write_config(provider: str, model: str | None) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f'provider = "{provider}"']
    if model:
        lines.append(f'model    = "{model}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _ok(f"wrote {CONFIG_FILE}")


def _smoke_test(provider_name: str, model: str | None) -> bool:
    from ocai.providers import ProviderError, get_provider
    print(f"\n{_dim('Smoke test: sending a trivial request...')}")
    try:
        provider = get_provider(provider_name, model=model)
        suggestion = provider.suggest("get the cluster version")
    except ProviderError as e:
        _fail(f"provider error: {e}")
        return False
    except Exception as e:  # noqa: BLE001 - we want to surface anything here
        _fail(f"{type(e).__name__}: {e}")
        return False
    _ok(f"provider returned: {_cyan(suggestion.command)}")
    return True


def run() -> int:
    print(_bold("ocai configure"))
    print(_dim("Interactive setup. Ctrl-C to abort at any time.\n"))
    _check_oc()
    print()
    print("Pick an AI backend:")
    print(f"  1. {_bold('claude')}  — Anthropic (needs API key)")
    print(f"  2. {_bold('openai')}  — OpenAI (needs API key)")
    print(f"  3. {_bold('ollama')}  — local, free, private (needs daemon)")
    try:
        choice = _ask("Choice", default="1").lower()
    except KeyboardInterrupt:
        print()
        return 130

    handlers = {
        "1": _configure_claude, "claude": _configure_claude,
        "2": _configure_openai, "openai": _configure_openai,
        "3": _configure_ollama, "ollama": _configure_ollama,
    }
    handler = handlers.get(choice)
    if not handler:
        _fail(f"unknown choice: {choice!r}")
        return 1

    try:
        result = handler()
    except KeyboardInterrupt:
        print()
        return 130

    _write_config(result["provider"], result.get("model"))

    if result.get("smoke_ok"):
        try:
            if _ask_yes("\nRun a smoke test (sends one request to the provider)?", default=True):
                if not _smoke_test(result["provider"], result.get("model")):
                    return 1
        except KeyboardInterrupt:
            print()
            return 130
    else:
        _warn("skipping smoke test (provider not ready yet — finish the steps above)")

    print()
    print(_bold(_green("All set.")))
    print(f"Try: {_cyan('ocai get all projects')}")
    return 0

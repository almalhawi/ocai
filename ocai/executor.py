from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass

from ocai.providers.base import Suggestion


class ExecutionRefused(RuntimeError):
    pass


# ANSI color helpers — only colorize when stdout is a TTY.
def _c(code: str) -> str:
    return code if sys.stdout.isatty() else ""


BOLD = _c("\033[1m")
DIM = _c("\033[2m")
RED = _c("\033[31m")
GREEN = _c("\033[32m")
YELLOW = _c("\033[33m")
CYAN = _c("\033[36m")
RESET = _c("\033[0m")


@dataclass
class ExecutionResult:
    returncode: int


def _validate(suggestion: Suggestion) -> None:
    cmd = suggestion.command.strip()
    if not cmd:
        raise ExecutionRefused("model returned an empty command")
    # Every segment of a pipeline should ultimately involve `oc` or a known
    # filter. We require that `oc` appears as a token somewhere — a weak but
    # cheap guard against the model returning unrelated shell.
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as e:
        raise ExecutionRefused(f"unparseable command: {e}")
    if "oc" not in tokens:
        raise ExecutionRefused(
            f"refusing to run: command does not invoke `oc` (got: {cmd!r})"
        )


def render(suggestion: Suggestion) -> None:
    label = f"{RED}destructive{RESET}" if suggestion.destructive else f"{GREEN}read-only{RESET}"
    print(f"{BOLD}Command{RESET}     ({label}):")
    print(f"  {CYAN}{suggestion.command}{RESET}")
    if suggestion.explanation:
        print(f"{BOLD}Explanation{RESET}: {DIM}{suggestion.explanation}{RESET}")


def _prompt_yes(destructive: bool) -> bool:
    if not sys.stdin.isatty():
        return False
    default = "y/N" if destructive else "Y/n"
    color = YELLOW if destructive else GREEN
    try:
        answer = input(f"{color}Run? [{default}]{RESET} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not answer:
        return not destructive
    return answer in {"y", "yes"}


def execute(suggestion: Suggestion, *, dry_run: bool, auto: bool) -> ExecutionResult:
    _validate(suggestion)
    render(suggestion)

    if dry_run:
        print(f"{DIM}(dry-run — not executing){RESET}")
        return ExecutionResult(returncode=0)

    if not auto and not _prompt_yes(suggestion.destructive):
        print(f"{DIM}aborted.{RESET}")
        return ExecutionResult(returncode=130)

    completed = subprocess.run(suggestion.command, shell=True)
    return ExecutionResult(returncode=completed.returncode)

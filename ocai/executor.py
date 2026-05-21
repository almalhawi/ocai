from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass

from ocai.providers.base import Suggestion


class ExecutionRefused(RuntimeError):
    pass


# Pipeline commands we'll let the model emit alongside `oc`. The model is
# instructed to use `oc` selectors first; this list is for the cases where
# a small filter is genuinely useful (counting, reshaping JSON).
ALLOWED_PIPE_TOOLS = frozenset({
    "oc", "jq", "xargs", "grep", "awk", "sed",
    "head", "tail", "sort", "uniq", "wc", "cut", "tr",
    "column", "tee", "cat",
})

# `oc` subcommands that mutate cluster state. The model also returns a
# `destructive` flag; we OR the two so either source can flag a command.
DESTRUCTIVE_VERBS = frozenset({
    "delete", "apply", "create", "replace", "patch", "edit",
    "scale", "rollout", "expose", "set", "adm", "label", "annotate",
    "debug", "exec", "cp", "port-forward", "new-app", "new-project",
    "new-build", "tag", "import-image", "process", "start-build",
    "cancel-build", "drain", "cordon", "uncordon", "login", "logout",
})

# Substrings whose presence anywhere in the command is an immediate refusal.
# These cover command substitution and process substitution, which would let
# the model smuggle an arbitrary command past a token-level allowlist.
_FORBIDDEN_SUBSTRINGS = ("`", "$(", ">(", "<(")


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
    executed: bool = False
    refine: str | None = None  # if set, caller should re-prompt with this text


def _tokenize(cmd: str) -> list[str]:
    """Tokenize a shell command, returning `|` and other shell metacharacters
    as standalone tokens (e.g. `;`, `&&`, `>`)."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def _is_destructive_command(tokens: list[str]) -> bool:
    """True if any `oc <verb>` in the token stream is in DESTRUCTIVE_VERBS."""
    for i, tok in enumerate(tokens):
        if tok == "oc" and i + 1 < len(tokens):
            if tokens[i + 1] in DESTRUCTIVE_VERBS:
                return True
    return False


def _validate(suggestion: Suggestion) -> list[str]:
    cmd = suggestion.command.strip()
    if not cmd:
        raise ExecutionRefused("model returned an empty command")

    for bad in _FORBIDDEN_SUBSTRINGS:
        if bad in cmd:
            raise ExecutionRefused(
                f"command contains forbidden shell construct {bad!r}: {cmd!r}"
            )

    try:
        tokens = _tokenize(cmd)
    except ValueError as e:
        raise ExecutionRefused(f"unparseable command: {e}")

    # Split into pipeline segments on `|`. Any other punctuation-only token
    # (`;`, `&&`, `||`, `&`, `>`, `<`, `(`, `)`, …) is a command chain or
    # redirect we don't allow — the model has no reason to emit them.
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok == "|":
            segments.append([])
            continue
        if tok and all(c in "();<>|&" for c in tok):
            raise ExecutionRefused(
                f"command contains forbidden shell operator {tok!r}: {cmd!r}"
            )
        segments[-1].append(tok)

    has_oc = False
    for seg in segments:
        if not seg:
            raise ExecutionRefused(f"empty pipeline segment in: {cmd!r}")
        first = seg[0]
        if first not in ALLOWED_PIPE_TOOLS:
            raise ExecutionRefused(
                f"pipeline command {first!r} is not in the allowlist "
                f"{sorted(ALLOWED_PIPE_TOOLS)}: {cmd!r}"
            )
        if first == "oc":
            has_oc = True

    if not has_oc:
        raise ExecutionRefused(
            f"refusing to run: command does not invoke `oc` (got: {cmd!r})"
        )

    # Defense in depth: a static look at the oc verb can flag commands as
    # destructive even if the model said otherwise.
    if _is_destructive_command(tokens):
        suggestion.destructive = True

    return tokens


def render(suggestion: Suggestion) -> None:
    label = f"{RED}destructive{RESET}" if suggestion.destructive else f"{GREEN}read-only{RESET}"
    print(f"{BOLD}Command{RESET}     ({label}):")
    print(f"  {CYAN}{suggestion.command}{RESET}")
    if suggestion.explanation:
        print(f"{BOLD}Explanation{RESET}: {DIM}{suggestion.explanation}{RESET}")


def _prompt_decision(destructive: bool) -> tuple[str, str | None]:
    """Returns one of ('run', None), ('abort', None), ('refine', <text>)."""
    if not sys.stdin.isatty():
        return ("abort", None)
    default = "y/N/r" if destructive else "Y/n/r"
    color = YELLOW if destructive else GREEN
    try:
        answer = input(f"{color}Run? [{default}]{RESET} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return ("abort", None)
    if not answer:
        return ("run", None) if not destructive else ("abort", None)
    if answer in {"y", "yes"}:
        return ("run", None)
    if answer in {"n", "no"}:
        return ("abort", None)
    if answer in {"r", "refine"}:
        try:
            text = input(f"{CYAN}Refine: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return ("abort", None)
        if not text:
            return ("abort", None)
        return ("refine", text)
    return ("abort", None)


def execute(suggestion: Suggestion, *, dry_run: bool, auto: bool) -> ExecutionResult:
    _validate(suggestion)
    render(suggestion)

    if dry_run:
        print(f"{DIM}(dry-run — not executing){RESET}")
        return ExecutionResult(returncode=0, executed=False)

    if not auto:
        decision, text = _prompt_decision(suggestion.destructive)
        if decision == "abort":
            print(f"{DIM}aborted.{RESET}")
            return ExecutionResult(returncode=130, executed=False)
        if decision == "refine":
            return ExecutionResult(returncode=0, executed=False, refine=text)

    completed = subprocess.run(suggestion.command, shell=True)
    return ExecutionResult(returncode=completed.returncode, executed=True)

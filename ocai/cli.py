from __future__ import annotations

import argparse
import sys

from ocai import __version__
from ocai import context as cluster_context
from ocai import history
from ocai.config import Config
from ocai.executor import ExecutionRefused, execute
from ocai.providers import ProviderError, get_provider


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ocai",
        description=(
            "AI-powered natural-language wrapper over the OpenShift `oc` CLI.\n"
            "By Nasser Almalhawi <almalhawi.nasser@gmail.com>"
        ),
        epilog=(
            "Examples:\n"
            "  ocai configure                       (interactive first-time setup)\n"
            "  ocai delete all completed builds\n"
            "  ocai get all pods on node worker-1\n"
            "  ocai deploy nginx webserver\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("request", nargs=argparse.REMAINDER, help="Natural-language request")
    p.add_argument(
        "--provider",
        choices=["claude", "openai", "ollama"],
        help="AI backend (default: from config or $OCAI_PROVIDER, else claude)",
    )
    p.add_argument("--model", help="Override model name for the chosen provider")
    p.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print the proposed command and exit without executing",
    )
    p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt (auto-execute)",
    )
    p.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Print effective config (provider, model, source) before running",
    )
    p.add_argument(
        "--no-context",
        action="store_true",
        help="Don't gather current oc context (project/user) to send with the prompt",
    )
    p.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"ocai {__version__} — by Nasser Almalhawi <almalhawi.nasser@gmail.com>",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    # `ocai configure` is a subcommand-style entry point. Intercepting before
    # argparse keeps the natural-language request flow ("ocai delete all …")
    # unchanged for every other call.
    if argv and argv[0] == "configure":
        from ocai.configure import run as run_configure
        return run_configure()

    parser = _build_parser()
    args = parser.parse_args(argv)

    request = " ".join(args.request).strip()
    if not request:
        parser.print_help(sys.stderr)
        return 2

    cfg = Config.load()
    provider_name = args.provider or cfg.provider
    model = args.model or cfg.model

    if args.debug:
        print(
            f"ocai: provider={provider_name!r} model={model!r} "
            f"config_source={cfg.source!r}",
            file=sys.stderr,
        )

    ctx = None if args.no_context else cluster_context.gather()
    if args.debug and ctx:
        print(f"ocai: cluster context:\n{ctx}", file=sys.stderr)

    try:
        provider = get_provider(provider_name, model=model)
    except ProviderError as e:
        print(f"ocai: provider error: {e}", file=sys.stderr)
        return 1

    # The refine loop lets the user iterate on the suggested command without
    # retyping the whole request. Capped to avoid runaway API calls.
    effective_request = request
    last_command: str | None = None
    for _attempt in range(5):
        try:
            suggestion = provider.suggest(effective_request, context=ctx)
        except ProviderError as e:
            print(f"ocai: provider error: {e}", file=sys.stderr)
            return 1

        log_entry: dict = {
            "prompt": effective_request,
            "command": suggestion.command,
            "destructive": suggestion.destructive,
            "provider": provider_name,
            "model": model,
        }

        try:
            result = execute(suggestion, dry_run=args.dry_run, auto=args.yes)
        except ExecutionRefused as e:
            print(f"ocai: refusing to execute: {e}", file=sys.stderr)
            history.record({**log_entry, "executed": False, "refused": str(e)})
            return 1

        if result.refine:
            history.record({**log_entry, "executed": False, "refined": result.refine})
            last_command = suggestion.command
            effective_request = (
                f"{request}\n"
                f"Previous attempt: {last_command}\n"
                f"Refinement: {result.refine}"
            )
            continue

        history.record({
            **log_entry,
            "executed": result.executed,
            "returncode": result.returncode if result.executed else None,
        })
        return result.returncode

    print("ocai: too many refinement attempts; aborting.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

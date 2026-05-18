from __future__ import annotations

import argparse
import sys

from ocai import __version__
from ocai.config import Config
from ocai.executor import ExecutionRefused, execute
from ocai.providers import ProviderError, get_provider


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ocai",
        description="AI-powered natural-language wrapper over the OpenShift `oc` CLI.",
        epilog=(
            "Examples:\n"
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
    p.add_argument("-V", "--version", action="version", version=f"ocai {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    request = " ".join(args.request).strip()
    if not request:
        parser.print_help(sys.stderr)
        return 2

    cfg = Config.load()
    provider_name = args.provider or cfg.provider
    model = args.model or cfg.model

    try:
        provider = get_provider(provider_name, model=model)
        suggestion = provider.suggest(request)
    except ProviderError as e:
        print(f"ocai: provider error: {e}", file=sys.stderr)
        return 1

    try:
        result = execute(suggestion, dry_run=args.dry_run, auto=args.yes)
    except ExecutionRefused as e:
        print(f"ocai: refusing to execute: {e}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())

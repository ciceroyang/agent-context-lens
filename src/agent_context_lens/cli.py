from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .scanner import scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-context-lens",
        description=(
            "Audit coding-agent instructions, skills, and MCP configuration "
            "without an API key."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--format",
        choices=("terminal", "json", "markdown"),
        default="terminal",
        help="Report format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the report to this file instead of stdout.",
    )
    parser.add_argument(
        "--fail-under",
        type=int,
        metavar="SCORE",
        help="Exit with status 2 when the score is below this value.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fail_under is not None and not 0 <= args.fail_under <= 100:
        raise SystemExit("--fail-under must be between 0 and 100")

    try:
        report = scan(args.path)
    except (OSError, ValueError) as error:
        print(f"agent-context-lens: {error}", file=sys.stderr)
        return 1

    if args.format == "json":
        rendered = report.to_json() + "\n"
    elif args.format == "markdown":
        rendered = report.to_markdown()
    else:
        rendered = report.to_terminal() + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if args.fail_under is not None and report.score < args.fail_under:
        return 2
    return 0


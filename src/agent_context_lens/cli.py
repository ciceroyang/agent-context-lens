from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .config_snapshot import build_explain_config
from .providers import explain_codex
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
    explain = parser.add_argument_group("Codex context explanation")
    explain.add_argument(
        "--explain",
        action="store_true",
        help="Explain a provider instruction chain instead of scanning.",
    )
    explain.add_argument(
        "--agent",
        choices=("codex",),
        help="Provider to explain (required with --explain).",
    )
    explain.add_argument(
        "--cwd",
        help="Working directory whose instruction chain should be explained.",
    )
    explain.add_argument(
        "--include-user",
        action="store_true",
        help="Opt in to inspecting user-global instruction files.",
    )
    explain.add_argument(
        "--config-snapshot",
        type=Path,
        help="Normalized JSON snapshot of effective Codex configuration.",
    )
    explain.add_argument(
        "--project-root",
        help="Declare the effective project root.",
    )
    explain.add_argument(
        "--root-marker",
        action="append",
        help="Declare a project root marker (repeatable).",
    )
    explain.add_argument(
        "--fallback-name",
        action="append",
        help="Declare a project instruction fallback filename (repeatable).",
    )
    explain.add_argument(
        "--max-bytes",
        type=int,
        help="Declare the Codex project instruction byte limit.",
    )
    explain.add_argument(
        "--project-trust",
        choices=("trusted", "untrusted", "unknown"),
        help="Declare the effective project trust state.",
    )
    explain.add_argument(
        "--codex-version",
        help="Declare the Codex CLI version used for comparison.",
    )
    explain.add_argument(
        "--behavior-profile",
        help="Select official-contract or an exact named evidence profile.",
    )
    explain.add_argument(
        "--fail-on-limitation",
        action="store_true",
        help="Exit with status 3 when an explain report has limitations.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.fail_under is not None and not 0 <= args.fail_under <= 100:
        raise SystemExit("--fail-under must be between 0 and 100")

    explain_only_used = any(
        (
            args.agent is not None,
            args.cwd is not None,
            args.include_user,
            args.config_snapshot is not None,
            args.project_root is not None,
            args.root_marker is not None,
            args.fallback_name is not None,
            args.max_bytes is not None,
            args.project_trust is not None,
            args.codex_version is not None,
            args.behavior_profile is not None,
            args.fail_on_limitation,
        )
    )
    if not args.explain and explain_only_used:
        parser.error("explain-only options require --explain")
    if args.explain and args.agent is None:
        parser.error("--agent is required with --explain")
    if args.explain and args.fail_under is not None:
        parser.error("--fail-under cannot be used with --explain")

    if args.explain:
        return _run_explain(args, parser)
    return _run_scan(args)


def _run_scan(args: argparse.Namespace) -> int:
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


def _run_explain(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> int:
    anchor = _absolute_lexical(args.path)
    cwd = _explain_cwd(args.cwd, anchor)
    project_root = (
        str(_absolute_lexical(args.project_root))
        if args.project_root is not None
        else None
    )
    try:
        config = build_explain_config(
            snapshot_path=args.config_snapshot,
            project_root=project_root,
            root_markers=args.root_marker,
            fallback_names=args.fallback_name,
            max_bytes=args.max_bytes,
            project_trust=args.project_trust,
            codex_version=args.codex_version,
            behavior_profile=args.behavior_profile,
        )
    except ValueError as error:
        parser.error(str(error))

    try:
        report = explain_codex(
            anchor,
            cwd=cwd,
            config=config,
            include_user=args.include_user,
        )
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

    if args.fail_on_limitation and report.has_limitations:
        return 3
    return 0


def _absolute_lexical(path: str | Path) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = Path.cwd() / value
    return Path(os.path.abspath(os.fspath(value)))


def _explain_cwd(value: str | None, anchor: Path) -> Path:
    if value is None:
        return anchor
    requested = Path(value).expanduser()
    if requested.is_absolute():
        return _absolute_lexical(requested)
    process_relative = _absolute_lexical(requested)
    try:
        process_relative.relative_to(anchor)
        process_is_within_anchor = True
    except ValueError:
        process_is_within_anchor = False
    if process_relative.exists() and process_is_within_anchor:
        return process_relative
    anchor_relative = _absolute_lexical(anchor / requested)
    if anchor_relative.exists():
        return anchor_relative
    return process_relative

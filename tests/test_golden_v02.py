from __future__ import annotations

import re
from pathlib import Path

from agent_context_lens import __version__
from agent_context_lens.config_snapshot import ConfigLayer, ExplainConfig
from agent_context_lens.providers.codex import explain_codex


REPOSITORY = Path(__file__).parents[1]
GOLDEN = Path(__file__).parent / "golden" / "v0_2"


def golden_report():
    root = REPOSITORY / "demo" / "monorepo"
    config = ExplainConfig(
        source="golden_fixture",
        project_root=str(root),
        project_root_markers=(".git",),
        root_markers_declared=True,
        fallback_filenames=(),
        project_doc_max_bytes=32768,
        project_trust="trusted",
        codex_version="unknown",
        behavior_profile="official-contract",
        platform="darwin-arm64",
        selected_profile=None,
        layers=(
            ConfigLayer("cli_override", "not_present"),
            ConfigLayer("trusted_project", "not_present"),
            ConfigLayer("selected_profile", "not_present"),
            ConfigLayer("user", "not_present"),
            ConfigLayer("system", "not_present"),
            ConfigLayer("defaults", "resolved"),
        ),
        direct_overrides=(),
    )
    return explain_codex(
        root,
        cwd=root / "services" / "payments",
        config=config,
    )


def test_v02_explain_renderer_goldens():
    report = golden_report()

    assert report.to_json().encode() == (GOLDEN / "explain.json").read_bytes()
    assert report.to_markdown().encode() == (
        GOLDEN / "explain.md"
    ).read_bytes()
    assert report.to_terminal().encode() == (
        GOLDEN / "explain-terminal.txt"
    ).read_bytes()


def test_v02_version_golden_matches_package_metadata():
    expected = f"agent-context-lens {__version__}\n".encode()
    assert (GOLDEN / "version.txt").read_bytes() == expected

    pyproject = (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    assert match is not None
    assert match.group(1) == __version__

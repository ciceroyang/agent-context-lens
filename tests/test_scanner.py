from __future__ import annotations

import json

from agent_context_lens.cli import main
from agent_context_lens.scanner import scan


def test_empty_repository_reports_missing_instructions(tmp_path):
    report = scan(tmp_path)

    assert report.score == 92
    assert report.files == ()
    assert [finding.code for finding in report.findings] == ["CTX001"]


def test_clean_agents_file_scores_100(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "# Instructions\n\nRun tests with `python -m pytest` before finishing.\n",
        encoding="utf-8",
    )

    report = scan(tmp_path)

    assert report.score == 100
    assert report.total_approx_tokens > 0
    assert report.findings == ()


def test_terminal_output_uses_singular_file_label(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "Verify with `python -m pytest`.\n",
        encoding="utf-8",
    )

    rendered = scan(tmp_path).to_terminal()

    assert "Context: 1 file ·" in rendered
    assert "1 files" not in rendered


def test_inline_mcp_secret_is_critical(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "Run tests with `python -m pytest`.\n",
        encoding="utf-8",
    )
    (tmp_path / ".mcp.json").write_text(
        '{"env": {"API_KEY": "sk-example-inline-secret-123"}}',
        encoding="utf-8",
    )

    report = scan(tmp_path)

    assert any(finding.code == "SEC001" for finding in report.findings)
    assert report.score == 75


def test_duplicate_instruction_lines_are_reported(tmp_path):
    duplicate = (
        "Always run the complete verification command before you finish a change.\n"
    )
    (tmp_path / "AGENTS.md").write_text(
        duplicate * 3 + "Run verification with `python -m pytest`.\n",
        encoding="utf-8",
    )
    nested = tmp_path / "packages" / "api"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text(duplicate * 3, encoding="utf-8")

    report = scan(tmp_path)

    assert report.duplicate_line_ratio >= 0.30
    assert any(finding.code == "CTX005" for finding in report.findings)


def test_json_cli_output(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text(
        "Verify with `python -m pytest`.\n",
        encoding="utf-8",
    )

    exit_code = main([str(tmp_path), "--format", "json"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert data["schema_version"] == 1
    assert data["score"] == 100


def test_fail_under_returns_two(tmp_path):
    assert main([str(tmp_path), "--fail-under", "100"]) == 2


def test_scan_recognizes_root_and_nested_agents_overrides(tmp_path):
    (tmp_path / "AGENTS.override.md").write_text(
        "Verify with `python -m pytest`.\n", encoding="utf-8"
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "AGENTS.override.md").write_text(
        "Nested override.\n", encoding="utf-8"
    )

    report = scan(tmp_path)

    assert [item.path for item in report.files] == [
        "AGENTS.override.md",
        "nested/AGENTS.override.md",
    ]
    assert not any(item.code == "CTX001" for item in report.findings)

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent_context_lens import __version__
from agent_context_lens import cli as cli_module
from agent_context_lens.cli import build_parser, main
from agent_context_lens.scanner import ContextFile, Report


GOLDEN = Path(__file__).parent / "golden"


def frozen_v01_report() -> Report:
    content = b"Run tests with `python -m pytest`.\n"
    context_file = ContextFile(
        path="AGENTS.md",
        category="instructions",
        bytes=len(content),
        lines=1,
        approx_tokens=9,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    return Report(
        root="/repo",
        score=100,
        files=(context_file,),
        findings=(),
        total_bytes=len(content),
        total_approx_tokens=9,
        duplicate_line_ratio=0.0,
    )


def test_schema_01_immutable_v01_serializer_goldens():
    report = frozen_v01_report()

    assert report.to_json().encode() == (
        GOLDEN / "v0_1" / "scan.json"
    ).read_bytes()
    assert report.to_markdown().encode() == (
        GOLDEN / "v0_1" / "scan.md"
    ).read_bytes()
    assert report.to_terminal().encode() == (
        GOLDEN / "v0_1" / "scan-terminal.txt"
    ).read_bytes()


@pytest.mark.parametrize(
    ("output_format", "golden_name", "cli_adds_newline"),
    [
        ("terminal", "scan-terminal.txt", True),
        ("json", "scan.json", True),
        ("markdown", "scan.md", False),
    ],
)
def test_cli_01_immutable_v01_output_bytes(
    monkeypatch,
    capsys,
    output_format,
    golden_name,
    cli_adds_newline,
):
    monkeypatch.setattr(
        cli_module, "scan", lambda _path: frozen_v01_report()
    )

    assert main([".", "--format", output_format]) == 0
    output = capsys.readouterr().out.encode()
    expected = (GOLDEN / "v0_1" / golden_name).read_bytes()
    if cli_adds_newline:
        expected += b"\n"
    assert output == expected


def test_cli_02_03_legacy_option_ordering(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text(
        "Verify with `python -m pytest`.\n", encoding="utf-8"
    )

    before = main(["--format", "json", str(tmp_path)])
    before_output = capsys.readouterr().out
    after = main([str(tmp_path), "--format", "json"])
    after_output = capsys.readouterr().out

    assert before == after == 0
    assert before_output == after_output
    assert json.loads(before_output)["schema_version"] == 1


def test_cli_04_help_retains_legacy_options_and_explain_group(capsys):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["--help"])

    output = capsys.readouterr().out
    assert error.value.code == 0
    for option in ("--format", "--output", "--fail-under", "--version"):
        assert option in output
    assert "Codex context explanation" in output
    assert "--explain" in output


def test_cli_05_missing_path_returns_one(tmp_path, capsys):
    exit_code = main([str(tmp_path / "missing")])

    assert exit_code == 1
    assert "Not a directory" in capsys.readouterr().err


def test_cli_06_directory_named_explain_remains_scan_path(
    tmp_path, monkeypatch, capsys
):
    directory = tmp_path / "explain"
    directory.mkdir()
    (directory / "AGENTS.md").write_text(
        "Verify with `python -m pytest`.\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(["explain"])

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("Agent Context Lens\n")


def test_cli_07_explain_mode_and_json_contract(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("project", encoding="utf-8")

    exit_code = main(
        [
            str(tmp_path),
            "--explain",
            "--agent",
            "codex",
            "--project-root",
            str(tmp_path),
            "--format",
            "json",
        ]
    )
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert data["report_type"] == "context_explain"
    assert data["instruction_scopes"][1] == {
        "scope": "user",
        "status": "not_requested",
        "reason_codes": ["user_scope_not_requested"],
    }


def test_root_07_cli_rejects_cwd_outside_explicit_root(tmp_path, capsys):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    exit_code = main(
        [
            str(root),
            "--explain",
            "--agent",
            "codex",
            "--cwd",
            str(outside),
            "--project-root",
            str(root),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "outside project root" in captured.err


def test_cli_relative_cwd_resolves_below_anchor(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    nested = repo / "nested"
    nested.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("root", encoding="utf-8")
    (nested / "AGENTS.md").write_text("nested", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert (
        main(
            [
                "repo",
                "--explain",
                "--agent",
                "codex",
                "--cwd",
                "nested",
                "--project-root",
                "repo",
                "--format",
                "json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)

    assert data["working_directory"] == "nested"


def test_cli_08_three_formats_share_state(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("project", encoding="utf-8")
    base = [
        str(tmp_path),
        "--explain",
        "--agent",
        "codex",
        "--project-root",
        str(tmp_path),
    ]
    outputs = {}
    for output_format in ("terminal", "json", "markdown"):
        assert main([*base, "--format", output_format]) == 0
        outputs[output_format] = capsys.readouterr().out

    for output in outputs.values():
        assert "AGENTS.md" in output
        assert "user_scope_not_requested" in output


def test_cli_09_explain_output_file_matches_stdout_renderer(
    tmp_path, capsys
):
    (tmp_path / "AGENTS.md").write_text("project", encoding="utf-8")
    output = tmp_path / "report.json"
    args = [
        str(tmp_path),
        "--explain",
        "--agent",
        "codex",
        "--project-root",
        str(tmp_path),
        "--format",
        "json",
    ]

    assert main(args) == 0
    expected = capsys.readouterr().out
    assert main([*args, "--output", str(output)]) == 0

    assert capsys.readouterr().out == ""
    assert output.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize(
    "args",
    [
        ["--explain", "--agent", "codex", "--fail-under", "80"],
        ["--include-user"],
        ["--cwd", "."],
        ["--behavior-profile", "official-contract"],
    ],
)
def test_cli_10_11_invalid_flag_combinations_exit_two(args):
    with pytest.raises(SystemExit) as error:
        main(args)

    assert error.value.code == 2


def test_cli_12_fail_on_limitation_exit_three(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("project", encoding="utf-8")
    base = [
        str(tmp_path),
        "--explain",
        "--agent",
        "codex",
        "--project-root",
        str(tmp_path),
    ]

    assert main(base) == 0
    capsys.readouterr()
    assert main([*base, "--fail-on-limitation"]) == 3


def test_cfg_09_cli_invalid_snapshot_exits_two(tmp_path):
    snapshot = tmp_path / "bad.json"
    snapshot.write_text('{"schema_version": 2}', encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main(
            [
                str(tmp_path),
                "--explain",
                "--agent",
                "codex",
                "--config-snapshot",
                str(snapshot),
            ]
        )

    assert error.value.code == 2


def test_version_interface_matches_package_metadata(
    capsys, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("--version must not inspect the filesystem")

    monkeypatch.setattr("agent_context_lens.cli.scan", forbidden)
    monkeypatch.setattr(
        "agent_context_lens.cli.build_explain_config", forbidden
    )
    monkeypatch.setattr("agent_context_lens.cli.explain_codex", forbidden)

    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out == f"agent-context-lens {__version__}\n"

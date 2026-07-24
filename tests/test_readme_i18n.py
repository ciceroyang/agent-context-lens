from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "scripts/check_readme_i18n.py"
SPEC = importlib.util.spec_from_file_location("acl_light_i18n_checker", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)

BASELINE = "e6498fbf7c1b89d368aea7fc42120357ef4bc27a"
I18N_WORKFLOW_BLOCK = """  i18n:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: python -m pip install "pytest>=8.0"
      - run: python scripts/check_readme_i18n.py --release-evidence
      - run: python -m pytest tests/test_readme_i18n.py
"""


def run(
    args: list[str],
    cwd: Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.run(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and process.returncode != 0:
        raise AssertionError(
            f"{args!r} failed\nstdout={process.stdout!r}\nstderr={process.stderr!r}"
        )
    return process


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], repo, check=check).stdout.decode("utf-8").strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    run(
        [
            "git",
            "-c",
            "user.name=I18N Fixture",
            "-c",
            "user.email=i18n-fixture@example.invalid",
            "commit",
            "-m",
            message,
        ],
        repo,
    )
    return git(repo, "rev-parse", "HEAD")


def copy_candidate_files(repo: Path) -> None:
    for relative in checker.CHANGED_PATHS:
        source = ROOT / relative
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


@pytest.fixture()
def valid_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    run(["git", "clone", "--quiet", "--no-local", str(ROOT), str(repo)], tmp_path)
    git(repo, "checkout", "--quiet", BASELINE)
    copy_candidate_files(repo)
    commit_all(repo, "synthetic light candidate")
    proof = checker.validate_repository(repo, release_evidence=True)
    assert proof["result"] == "pass", proof
    return repo


def assert_error(repo: Path, code: str, *, release: bool = False) -> dict[str, object]:
    proof = checker.validate_repository(repo, release_evidence=release)
    assert proof["result"] == "fail", proof
    assert code in proof["error_codes"], proof
    return proof


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, separators=(",", ": ")) + "\n",
        encoding="utf-8",
    )


def mutate_metadata(repo: Path, locale: str, mutate: Callable[[dict[str, object]], None]) -> None:
    path = repo / checker.VISIBLE[locale]["file"]
    data = path.read_bytes()
    marker = b"<!-- i18n-light-meta\n"
    start = data.index(marker) + len(marker)
    end = data.index(b"-->\n", start)
    metadata = json.loads(data[start:end].decode("utf-8"))
    mutate(metadata)
    path.write_bytes(data[:start] + checker.json_bytes(metadata) + data[end:])


def cli(repo: Path, *args: str, python: str | None = None) -> subprocess.CompletedProcess[bytes]:
    return run(
        [python or sys.executable, "scripts/check_readme_i18n.py", *args],
        repo,
        check=False,
    )


def expected_proof(
    repo: Path,
    *,
    mode: str,
    result: str = "pass",
    errors: list[str] | None = None,
) -> bytes:
    manifest_sha = hashlib.sha256(
        (repo / "docs/i18n/source_manifest.json").read_bytes()
    ).hexdigest()
    checked = git(repo, "rev-parse", "HEAD") if mode == "release-evidence" else None
    proof = {
        "baseline_commit": BASELINE,
        "checked_commit": checked,
        "contract_id": "I18N-001-LIGHT",
        "error_codes": errors or [],
        "human_evidence_required": False,
        "locales": ["ja", "zh-CN"],
        "mode": mode,
        "product_version": "0.2.0",
        "result": result,
        "schema_version": 2,
        "source_manifest_sha256": manifest_sha,
    }
    return (
        json.dumps(proof, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def test_valid_development_and_release_pass(valid_repo: Path) -> None:
    development = checker.validate_repository(valid_repo)
    release = checker.validate_repository(valid_repo, release_evidence=True)
    assert development["result"] == "pass"
    assert development["checked_commit"] is None
    assert release["result"] == "pass"
    assert re.fullmatch(r"[0-9a-f]{40}", release["checked_commit"])


def test_base_01_02_03_frozen_identity(valid_repo: Path) -> None:
    baseline = run(["git", "show", f"{BASELINE}:README.md"], valid_repo).stdout
    assert len(baseline) == 8926
    assert len(baseline.splitlines()) == 271
    assert hashlib.sha256(baseline).hexdigest() == checker.BASELINE_README_SHA256
    assert git(valid_repo, "merge-base", "--is-ancestor", BASELINE, "HEAD") == ""
    assert checker.extract_literal_version(
        run(["git", "show", f"{BASELINE}:src/agent_context_lens/__init__.py"], valid_repo).stdout,
        checker.Issues(),
    ) == "0.2.0"


def test_file_01_exact_changed_path_status(valid_repo: Path) -> None:
    process = run(
        [
            "git", "-c", "core.quotepath=false", "diff", "--name-status", "-z",
            "--no-renames", BASELINE, "HEAD", "--",
        ],
        valid_repo,
    )
    observed = checker.parse_name_status(process.stdout, checker.Issues())
    expected_rows = [
        (relative, checker.CHANGED_STATUS[relative])
        for relative in sorted(
            checker.CHANGED_STATUS,
            key=lambda value: value.encode("utf-8"),
        )
    ]
    assert observed == checker.CHANGED_STATUS
    assert list(observed.items()) == expected_rows


def test_file_02_and_light_01_02_heavy_inputs_absent(valid_repo: Path) -> None:
    for relative in checker.FORBIDDEN_PATHS:
        assert not (valid_repo / relative).exists()
    source = (valid_repo / "scripts/check_readme_i18n.py").read_text()
    imports = checker.imported_modules(source, checker.Issues())
    assert not imports.intersection(
        {"agent_context_lens", "urllib", "socket", "requests", "http", "ftplib"}
    )
    manifest = read_json(valid_repo / "docs/i18n/source_manifest.json")
    assert not checker.recursive_keys(manifest).intersection(checker.FORBIDDEN_MACHINE_KEYS)


def test_file_02_unlisted_locale_fixture_fails(valid_repo: Path) -> None:
    (valid_repo / "tests/fixtures/i18n/README.fr.visible.md").write_text("extra\n")
    assert_error(valid_repo, "FILE")


@pytest.mark.parametrize("locale", ("zh-CN", "ja"))
def test_nav_01_notice_01_03_and_claim_01_exact_goldens(
    valid_repo: Path, locale: str
) -> None:
    data = (valid_repo / checker.VISIBLE[locale]["file"]).read_bytes()
    visible, metadata = checker.strip_localized(data, locale, checker.Issues())
    fixture = (valid_repo / checker.VISIBLE[locale]["fixture"]).read_bytes()
    assert visible == fixture
    assert metadata is not None
    lines = visible.decode().splitlines()
    assert lines[:3] == ["# Agent Context Lens", "", checker.VISIBLE[locale]["nav"]]
    assert lines[4] == checker.VISIBLE[locale]["notice"]


@pytest.mark.parametrize("mutation", ("missing", "renamed", "duplicate", "reordered", "redirected"))
def test_nav_02_mutations_fail(valid_repo: Path, mutation: str) -> None:
    path = valid_repo / "README.zh-CN.md"
    text = path.read_text()
    nav = checker.VISIBLE["zh-CN"]["nav"]
    if mutation == "missing":
        changed = text.replace("[日本語](README.ja.md)", "日本語", 1)
    elif mutation == "renamed":
        changed = text.replace("README.ja.md", "README.jp.md", 1)
    elif mutation == "duplicate":
        changed = text.replace(nav, nav + " | " + nav, 1)
    elif mutation == "reordered":
        changed = text.replace(nav, "[日本語](README.ja.md) | **简体中文** | [English](README.md)", 1)
    else:
        changed = text.replace("README.md)", "https://example.invalid/README.md)", 1)
    path.write_text(changed)
    assert_error(valid_repo, "NAV")


@pytest.mark.parametrize("locale", ("zh-CN", "ja"))
@pytest.mark.parametrize("clause", (0, 1, 2))
def test_notice_02_one_clause_mutations_fail(
    valid_repo: Path, locale: str, clause: int
) -> None:
    path = valid_repo / checker.VISIBLE[locale]["file"]
    notice = checker.VISIBLE[locale]["notice"]
    pieces = (
        ["面向社区的非官方翻译", "可能落后", "以英文 README 为准"]
        if locale == "zh-CN"
        else ["コミュニティ向けの非公式翻訳", "更新が遅れる場合", "英語版 README を正"]
    )
    path.write_text(path.read_text().replace(pieces[clause], "X", 1))
    assert_error(valid_repo, "NOTICE")


def test_ia_01_heading_and_line_limit_fail(valid_repo: Path) -> None:
    path = valid_repo / "README.ja.md"
    path.write_text(path.read_text().replace("## 主な機能", "## 追加\n\n## 主な機能", 1))
    assert_error(valid_repo, "IA")


def test_claim_02_added_or_paraphrased_prose_fails(valid_repo: Path) -> None:
    path = valid_repo / "README.zh-CN.md"
    path.write_text(path.read_text().replace("## 核心能力", "额外产品声明。\n\n## 核心能力", 1))
    assert_error(valid_repo, "CLAIM")


@pytest.mark.parametrize(
    "mutation",
    ("empty", "moved", "shortened", "expanded", "overlap", "omitted", "rebound"),
)
def test_source_01_02_04_mutations_fail(valid_repo: Path, mutation: str) -> None:
    path = valid_repo / "README.md"
    text = path.read_text()
    if mutation == "empty":
        changed = re.sub(
            r"(<!-- i18n-source:start:intro -->\n).*?(<!-- i18n-source:end:intro -->)",
            r"\1\2",
            text,
            count=1,
            flags=re.DOTALL,
        )
    elif mutation == "moved":
        marker = "<!-- i18n-source:start:intro -->\n"
        changed = text.replace(marker, "", 1).replace("# Why this exists\n", marker + "# Why this exists\n", 1)
    elif mutation == "shortened":
        changed = text.replace(
            "Agent Context Lens maps that dependency locally.",
            "Agent Context Lens maps that dependency.",
            1,
        )
    elif mutation == "expanded":
        changed = text.replace(
            "Agent Context Lens maps that dependency locally.",
            "Agent Context Lens maps that dependency locally. Extra.",
            1,
        )
    elif mutation == "overlap":
        changed = text.replace(
            "<!-- i18n-source:end:capabilities -->",
            "<!-- i18n-source:end:limitations -->",
            1,
        )
    elif mutation == "omitted":
        changed = text.replace("<!-- i18n-source:end:feedback -->\n", "", 1)
    else:
        changed = text.replace("acl-i18n-feedback", "acl-i18n-feedback-new", 1)
    path.write_text(changed)
    assert_error(valid_repo, "SOURCE")


def test_source_03_forward_and_reverse_match(valid_repo: Path) -> None:
    issues = checker.Issues()
    records = checker.proposal_records(issues)
    baseline = run(["git", "show", f"{BASELINE}:README.md"], valid_repo).stdout
    integrated = (valid_repo / "README.md").read_bytes()
    assert checker.apply_proposal(baseline, records) == integrated
    assert checker.reverse_proposal(integrated, records, issues) == baseline
    assert not issues.codes


@pytest.mark.parametrize("target", ("manifest", "metadata"))
def test_meta_01_exact_schema_mutations_fail(valid_repo: Path, target: str) -> None:
    if target == "manifest":
        path = valid_repo / "docs/i18n/source_manifest.json"
        value = read_json(path)
        value["schema_version"] = 4
        write_json(path, value)
    else:
        mutate_metadata(valid_repo, "ja", lambda value: value.update(schema_version=3))
    assert_error(valid_repo, "META")


@pytest.mark.parametrize("forbidden", checker.FORBIDDEN_MACHINE_KEYS)
def test_meta_02_forbidden_machine_keys_fail(valid_repo: Path, forbidden: str) -> None:
    path = valid_repo / "docs/i18n/source_manifest.json"
    value = read_json(path)
    value[forbidden] = "forbidden"
    write_json(path, value)
    assert_error(valid_repo, "HEAVY_GATE")


def test_command_01_exact_parity(valid_repo: Path) -> None:
    issues = checker.Issues()
    english = checker.extract_commands((valid_repo / "README.md").read_bytes(), issues)
    for locale in ("zh-CN", "ja"):
        localized = checker.extract_commands(
            (valid_repo / checker.VISIBLE[locale]["file"]).read_bytes(),
            issues,
        )
        assert localized == english
    assert not issues.codes


@pytest.mark.parametrize(
    "mutation",
    ("flag", "quote", "whitespace", "continuation", "marker", "fence", "order", "duplicate"),
)
def test_command_02_mutations_fail(valid_repo: Path, mutation: str) -> None:
    path = valid_repo / "README.zh-CN.md"
    text = path.read_text()
    if mutation == "flag":
        changed = text.replace("--project-root", "--project-roox", 1)
    elif mutation == "quote":
        changed = text.replace('"git+https://', "'git+https://", 1)
    elif mutation == "whitespace":
        changed = text.replace("agent-context-lens /path", "agent-context-lens  /path", 1)
    elif mutation == "continuation":
        changed = text.replace("repository \\\n", "repository\n", 1)
    elif mutation == "marker":
        changed = text.replace("start:QS-01", "start:QS-1", 1)
    elif mutation == "fence":
        changed = text.replace("```bash", "```sh", 1)
    elif mutation == "order":
        first = "<!-- i18n-command:start:QS-01 -->"
        second = "<!-- i18n-command:start:QS-02 -->"
        changed = text.replace(first, "TEMP", 1).replace(second, first, 1).replace("TEMP", second, 1)
    else:
        block = "<!-- i18n-command:start:QS-01 -->\n"
        changed = text.replace(block, block + block, 1)
    path.write_text(changed)
    assert_error(valid_repo, "COMMAND")


@pytest.mark.parametrize("locale", ("zh-CN", "ja"))
def test_token_01_mutation_fails(valid_repo: Path, locale: str) -> None:
    path = valid_repo / checker.VISIBLE[locale]["file"]
    path.write_text(path.read_text().replace("`official_contract`", "`official_contracx`", 1))
    assert_error(valid_repo, "TOKEN")


@pytest.mark.parametrize("locale", ("zh-CN", "ja"))
def test_statement_01_mutation_fails(valid_repo: Path, locale: str) -> None:
    path = valid_repo / checker.VISIBLE[locale]["file"]
    statement = checker.STATEMENTS[locale]["SAFE-NO-CONTENT"]
    path.write_text(path.read_text().replace(statement, statement + "!", 1))
    assert_error(valid_repo, "STATEMENT")


@pytest.mark.parametrize("target", ("README.md", "anchor", "SECURITY.md"))
def test_link_01_local_target_mutations_fail(valid_repo: Path, target: str) -> None:
    path = valid_repo / "README.ja.md"
    text = path.read_text()
    if target == "README.md":
        changed = text.replace("](README.md)", "](README-X.md)")
    elif target == "anchor":
        changed = text.replace("#acl-i18n-feedback", "#missing-anchor", 1)
    else:
        changed = text.replace("](SECURITY.md)", "](SECURITY-X.md)", 1)
    path.write_text(changed)
    assert_error(valid_repo, "LINK")


def test_link_02_external_and_redaction_mutations_fail(valid_repo: Path) -> None:
    path = valid_repo / "README.zh-CN.md"
    text = path.read_text()
    path.write_text(
        text.replace(
            "https://github.com/ciceroyang/agent-context-lens/discussions/1",
            "http://github.com/ciceroyang/agent-context-lens/discussions/1",
            1,
        )
    )
    assert_error(valid_repo, "LINK")


@pytest.mark.parametrize(
    "source",
    (
        "x = '0.2.0'\n",
        "__version__ = make_version()\n",
        "__version__ = '0.2.0'\n__version__ = '0.2.1'\n",
        "__version__: str = '0.2.0'\n",
        "__version__ = 'not-a-version'\n",
    ),
)
def test_version_01_ast_mutations_fail(valid_repo: Path, source: str) -> None:
    (valid_repo / "src/agent_context_lens/__init__.py").write_text(source)
    assert_error(valid_repo, "VERSION")


@pytest.mark.parametrize(
    "mutation",
    ("bom", "invalid", "crlf", "lone-cr", "missing-final-lf", "multiple-final-lf"),
)
def test_encoding_01_matrix(valid_repo: Path, mutation: str) -> None:
    path = valid_repo / "README.zh-CN.md"
    data = path.read_bytes()
    if mutation == "bom":
        changed = b"\xef\xbb\xbf" + data
    elif mutation == "invalid":
        changed = data[:10] + b"\xff" + data[10:]
    elif mutation == "crlf":
        changed = data.replace(b"\n", b"\r\n")
    elif mutation == "lone-cr":
        changed = data[:10] + b"\r" + data[10:]
    elif mutation == "missing-final-lf":
        changed = data.rstrip(b"\n")
    else:
        changed = data + b"\n"
    path.write_bytes(changed)
    assert_error(valid_repo, "ENCODING")


def test_path_01_file_symlink_and_external_target_fail(valid_repo: Path, tmp_path: Path) -> None:
    external = tmp_path / "external.md"
    external.write_text("external\n")
    path = valid_repo / "README.zh-CN.md"
    path.unlink()
    path.symlink_to(external)
    assert_error(valid_repo, "PATH")


def test_path_01_parent_symlink_fails(valid_repo: Path, tmp_path: Path) -> None:
    external = tmp_path / "outside-i18n"
    shutil.copytree(valid_repo / "docs/i18n", external)
    shutil.rmtree(valid_repo / "docs/i18n")
    (valid_repo / "docs/i18n").symlink_to(external, target_is_directory=True)
    assert_error(valid_repo, "PATH")


def test_path_01_fifo_and_directory_fail(valid_repo: Path) -> None:
    path = valid_repo / "README.zh-CN.md"
    path.unlink()
    os.mkfifo(path)
    assert_error(valid_repo, "PATH")


def test_path_01_directory_input_fails(valid_repo: Path) -> None:
    path = valid_repo / "README.zh-CN.md"
    path.unlink()
    path.mkdir()
    assert_error(valid_repo, "PATH")


def test_blob_01_working_bytes_and_dirty_state_fail(valid_repo: Path) -> None:
    path = valid_repo / "README.zh-CN.md"
    path.write_bytes(path.read_bytes() + b"x")
    proof = assert_error(valid_repo, "BLOB", release=True)
    assert "DIRTY" in proof["error_codes"]


def test_blob_01_tracked_symlink_mode_fails(valid_repo: Path, tmp_path: Path) -> None:
    external = tmp_path / "external.md"
    external.write_text("external\n")
    path = valid_repo / "README.zh-CN.md"
    path.unlink()
    path.symlink_to(external)
    commit_all(valid_repo, "tracked external symlink")
    assert_error(valid_repo, "BLOB", release=True)


@pytest.mark.parametrize(
    "relative",
    ("src/unauthorized.py", "pyproject-extra.toml", "LICENSE.extra", "docs/unrelated.md"),
)
def test_evidence_02_unauthorized_committed_paths_fail(
    valid_repo: Path, relative: str
) -> None:
    path = valid_repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("unauthorized\n")
    commit_all(valid_repo, f"unauthorized {relative}")
    assert_error(valid_repo, "BLOB", release=True)


def test_cli_01_02_exact_vectors_and_bytes(valid_repo: Path) -> None:
    development = cli(valid_repo)
    assert (development.returncode, development.stdout, development.stderr) == (
        0,
        expected_proof(valid_repo, mode="development"),
        b"",
    )
    release = cli(valid_repo, "--release-evidence")
    assert (release.returncode, release.stdout, release.stderr) == (
        0,
        expected_proof(valid_repo, mode="release-evidence"),
        b"",
    )
    help_result = cli(valid_repo, "--help")
    assert (help_result.returncode, help_result.stdout, help_result.stderr) == (
        0,
        checker.USAGE.encode(),
        b"",
    )
    for args in (
        ("--unknown",),
        ("--release-evidence", "--release-evidence"),
        ("--help", "--release-evidence"),
    ):
        invalid = cli(valid_repo, *args)
        assert (invalid.returncode, invalid.stdout, invalid.stderr) == (
            2,
            b"",
            b"ERROR CLI invalid arguments\n" + checker.USAGE.encode(),
        )


def test_cli_02_wrong_repository_bytes(tmp_path: Path) -> None:
    copied = tmp_path / "check_readme_i18n.py"
    shutil.copy2(CHECKER_PATH, copied)
    result = run([sys.executable, str(copied)], tmp_path, check=False)
    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        b"",
        b"ERROR REPO wrong repository context\n",
    )


def test_cli_02_caught_startup_bytes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def explode() -> Path:
        raise RuntimeError("synthetic")

    monkeypatch.setattr(checker, "initialize_repository", explode)
    assert checker.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR STARTUP checker initialization failed\n"


def test_cli_02_validation_fail_json_and_stderr(valid_repo: Path) -> None:
    path = valid_repo / "README.zh-CN.md"
    path.write_text(path.read_text().replace("`official_contract`", "`wrong`", 1))
    result = cli(valid_repo)
    proof = json.loads(result.stdout)
    assert result.returncode == 1
    assert proof["result"] == "fail"
    assert proof["checked_commit"] is None
    assert proof["error_codes"] == sorted(set(proof["error_codes"]))
    assert result.stderr == b"".join(
        f"ERROR {code}\n".encode() for code in proof["error_codes"]
    )


def test_cli_03_development_ignores_dirt_release_requires_it(valid_repo: Path) -> None:
    (valid_repo / "untracked.txt").write_text("dirty\n")
    assert checker.validate_repository(valid_repo)["result"] == "pass"
    release = assert_error(valid_repo, "DIRTY", release=True)
    assert release["checked_commit"] == git(valid_repo, "rev-parse", "HEAD")


def test_cli_03_shallow_history_only_fails_release(valid_repo: Path, tmp_path: Path) -> None:
    shallow = tmp_path / "shallow"
    run(
        ["git", "clone", "--quiet", "--depth", "1", f"file://{valid_repo}", str(shallow)],
        tmp_path,
    )
    assert checker.validate_repository(shallow)["result"] == "pass"
    assert_error(shallow, "HISTORY", release=True)


def test_cli_03_missing_baseline_only_fails_release(valid_repo: Path, tmp_path: Path) -> None:
    orphan = tmp_path / "missing-baseline"
    shutil.copytree(valid_repo, orphan, ignore=shutil.ignore_patterns(".git"))
    run(["git", "init", "--quiet"], orphan)
    commit_all(orphan, "orphan candidate")
    assert checker.validate_repository(orphan)["result"] == "pass"
    assert_error(orphan, "HISTORY", release=True)


def test_cli_03_non_ancestor_baseline_fails_release(valid_repo: Path) -> None:
    git(valid_repo, "checkout", "--orphan", "synthetic-orphan")
    commit_all(valid_repo, "non-ancestor candidate")
    assert checker.validate_repository(valid_repo)["result"] == "pass"
    assert_error(valid_repo, "HISTORY", release=True)


@pytest.mark.parametrize("mutation", ("modified", "staged", "deleted"))
def test_evidence_01_whole_tree_states_fail_release(
    valid_repo: Path, mutation: str
) -> None:
    path = valid_repo / "README.ja.md"
    if mutation == "deleted":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"x")
        if mutation == "staged":
            git(valid_repo, "add", "README.ja.md")
    assert_error(valid_repo, "DIRTY", release=True)


@pytest.mark.parametrize(
    "mutation",
    (
        "fully-commented-job",
        "commented-fetch-depth",
        "commented-python-version",
        "commented-run",
        "unrelated-job",
        "wrong-indentation",
        "duplicate-job",
        "false-job-condition",
        "false-step-condition",
        "continue-on-error",
        "wrong-fetch-depth",
        "wrong-python",
        "masked-command",
    ),
)
def test_ci_01_original_active_job_negatives(valid_repo: Path, mutation: str) -> None:
    path = valid_repo / ".github/workflows/ci.yml"
    text = path.read_text()
    assert text.count(I18N_WORKFLOW_BLOCK) == 1
    if mutation == "fully-commented-job":
        changed = "".join(f"# {line}" for line in I18N_WORKFLOW_BLOCK.splitlines(keepends=True))
    elif mutation == "commented-fetch-depth":
        changed = I18N_WORKFLOW_BLOCK.replace("          fetch-depth: 0", "          # fetch-depth: 0")
    elif mutation == "commented-python-version":
        changed = I18N_WORKFLOW_BLOCK.replace('          python-version: "3.10"', '          # python-version: "3.10"')
    elif mutation == "commented-run":
        changed = I18N_WORKFLOW_BLOCK.replace(
            "      - run: python scripts/check_readme_i18n.py --release-evidence",
            "      # - run: python scripts/check_readme_i18n.py --release-evidence",
        )
    elif mutation == "unrelated-job":
        changed = I18N_WORKFLOW_BLOCK.replace("  i18n:", "  documentation:", 1)
    elif mutation == "wrong-indentation":
        changed = "".join("  " + line for line in I18N_WORKFLOW_BLOCK.splitlines(keepends=True))
    elif mutation == "duplicate-job":
        changed = I18N_WORKFLOW_BLOCK + "\n" + I18N_WORKFLOW_BLOCK
    elif mutation == "false-job-condition":
        changed = I18N_WORKFLOW_BLOCK.replace("  i18n:\n", "  i18n:\n    if: ${{ false }}\n", 1)
    elif mutation == "false-step-condition":
        changed = I18N_WORKFLOW_BLOCK.replace(
            "      - run: python scripts/check_readme_i18n.py --release-evidence",
            "      - run: python scripts/check_readme_i18n.py --release-evidence\n        if: ${{ false }}",
        )
    elif mutation == "continue-on-error":
        changed = I18N_WORKFLOW_BLOCK.replace(
            "      - run: python scripts/check_readme_i18n.py --release-evidence",
            "      - run: python scripts/check_readme_i18n.py --release-evidence\n        continue-on-error: true",
        )
    elif mutation == "wrong-fetch-depth":
        changed = I18N_WORKFLOW_BLOCK.replace("fetch-depth: 0", "fetch-depth: 1")
    elif mutation == "wrong-python":
        changed = I18N_WORKFLOW_BLOCK.replace('python-version: "3.10"', 'python-version: "3.11"')
    else:
        changed = I18N_WORKFLOW_BLOCK.replace(
            "python scripts/check_readme_i18n.py --release-evidence",
            "python scripts/check_readme_i18n.py --release-evidence || true",
        )
    path.write_text(text.replace(I18N_WORKFLOW_BLOCK, changed, 1))
    assert_error(valid_repo, "CI")


@pytest.mark.parametrize("placement", ("before", "after"))
@pytest.mark.parametrize(
    ("scope", "duplicate"),
    (
        ("jobs", "jobs: {}"),
        ("jobs", "jobs: &disabled {}"),
        ("jobs", '"jobs": {}'),
        ("jobs", "!!str jobs: {}"),
        ("i18n", "  i18n: {}"),
        ("i18n", "  i18n: &disabled {}"),
        ("i18n", '  "i18n": {}'),
        ("i18n", "  !!str i18n: {}"),
    ),
)
def test_ci_02_reserved_mapping_negatives(
    valid_repo: Path, placement: str, scope: str, duplicate: str
) -> None:
    path = valid_repo / ".github/workflows/ci.yml"
    text = path.read_text()
    line = duplicate + "\n"
    if scope == "jobs":
        changed = (
            text.replace("jobs:\n", line + "jobs:\n", 1)
            if placement == "before"
            else text.rstrip() + "\n\n" + line
        )
    else:
        changed = text.replace(
            I18N_WORKFLOW_BLOCK,
            line + I18N_WORKFLOW_BLOCK
            if placement == "before"
            else I18N_WORKFLOW_BLOCK + "\n" + line,
            1,
        )
    path.write_text(changed)
    assert_error(valid_repo, "CI")


@pytest.mark.parametrize(
    "mutation",
    (
        "remove-checker", "remove-test", "reverse-commands", "disable-checker",
        "disable-test", "continue-checker", "continue-test", "mask-checker",
        "mask-test",
    ),
)
def test_ci_02_light_command_negatives(valid_repo: Path, mutation: str) -> None:
    path = valid_repo / ".github/workflows/ci.yml"
    text = path.read_text()
    checker_line = "      - run: python scripts/check_readme_i18n.py --release-evidence"
    test_line = "      - run: python -m pytest tests/test_readme_i18n.py"
    if mutation == "remove-checker":
        changed = text.replace(checker_line + "\n", "", 1)
    elif mutation == "remove-test":
        changed = text.replace(test_line + "\n", "", 1)
    elif mutation == "reverse-commands":
        changed = text.replace(checker_line + "\n" + test_line, test_line + "\n" + checker_line, 1)
    elif mutation == "disable-checker":
        changed = text.replace(checker_line, checker_line + "\n        if: ${{ false }}", 1)
    elif mutation == "disable-test":
        changed = text.replace(test_line, test_line + "\n        if: ${{ false }}", 1)
    elif mutation == "continue-checker":
        changed = text.replace(checker_line, checker_line + "\n        continue-on-error: true", 1)
    elif mutation == "continue-test":
        changed = text.replace(test_line, test_line + "\n        continue-on-error: true", 1)
    elif mutation == "mask-checker":
        changed = text.replace(checker_line, checker_line + " || true", 1)
    else:
        changed = text.replace(test_line, test_line + " || true", 1)
    path.write_text(changed)
    assert_error(valid_repo, "CI")


@pytest.mark.parametrize(
    ("scope", "duplicate"),
    (
        ("jobs", "'jobs': {}"),
        ("jobs", "jobs : {}"),
        ("jobs", "\tjobs: {}"),
        ("jobs", " jobs: {}"),
        ("i18n", "  'i18n': {}"),
        ("i18n", "  i18n : {}"),
        ("i18n", "\ti18n: {}"),
        ("i18n", "   i18n: {}"),
    ),
)
def test_ci_02_unsupported_mapping_forms_fail_closed(
    valid_repo: Path, scope: str, duplicate: str
) -> None:
    path = valid_repo / ".github/workflows/ci.yml"
    text = path.read_text()
    line = duplicate + "\n"
    if scope == "jobs":
        changed = text.replace("jobs:\n", line + "jobs:\n", 1)
    else:
        changed = text.replace(I18N_WORKFLOW_BLOCK, line + I18N_WORKFLOW_BLOCK, 1)
    path.write_text(changed)
    assert_error(valid_repo, "CI")


def test_ci_02_inventory_is_exact_38(valid_repo: Path) -> None:
    inventory = read_json(valid_repo / "tests/fixtures/i18n/mutation_cases.json")
    assert inventory["workflow_negative_cases"] == checker.WORKFLOW_NEGATIVES
    assert inventory["workflow_negative_count"] == 38
    assert len(set(inventory["workflow_negative_cases"])) == 38


def test_acceptance_inventory_has_all_41_unique_ids(valid_repo: Path) -> None:
    inventory = read_json(valid_repo / "tests/fixtures/i18n/mutation_cases.json")
    assert inventory["acceptance_ids"] == checker.ACCEPTANCE_IDS
    assert len(inventory["acceptance_ids"]) == 41
    assert len(set(inventory["acceptance_ids"])) == 41


@pytest.mark.parametrize("locale", ("zh-CN", "ja"))
@pytest.mark.parametrize("phrase_index", range(6))
def test_light_03_forbidden_human_validation_claims_fail(
    valid_repo: Path, locale: str, phrase_index: int
) -> None:
    path = valid_repo / checker.VISIBLE[locale]["file"]
    phrase = checker.FORBIDDEN_IMPLICATIONS[locale][phrase_index]
    path.write_text(path.read_text().replace(
        checker.VISIBLE[locale]["headings"][-1],
        phrase + "\n\n" + checker.VISIBLE[locale]["headings"][-1],
        1,
    ))
    proof = checker.validate_repository(valid_repo)
    assert "CLAIM" in proof["error_codes"]


def test_nonclaim_01_proof_has_only_mechanical_fields(valid_repo: Path) -> None:
    proof = checker.validate_repository(valid_repo)
    serialized = json.dumps(proof, sort_keys=True)
    for forbidden in (
        "reviewed", "current", "supported", "native", "semantic",
        "community-maintained", "maintainer",
    ):
        assert forbidden not in serialized


def test_auth_01_no_publication_authority_or_network(valid_repo: Path) -> None:
    source = (valid_repo / "scripts/check_readme_i18n.py").read_text()
    assert "git push" not in source
    assert "pull request" not in source.lower()
    assert "release create" not in source.lower()
    assert checker.validate_repository(valid_repo)["human_evidence_required"] is False

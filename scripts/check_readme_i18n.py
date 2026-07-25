#!/usr/bin/env python3
"""Validate the frozen I18N-001-LIGHT mechanical documentation contract."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any


BASELINE = "e6498fbf7c1b89d368aea7fc42120357ef4bc27a"
VERSION = "0.2.0"
CONTRACT_ID = "I18N-001-LIGHT"
PROPOSAL_SHA256 = "e8dabc6dfa0e9f803b035324bdba416095a7583ced36fb37023a0b0d7d9faa57"
BASELINE_README_SHA256 = "c5c3cf854731e067ab88ede40551260932a8ff4423304420c309716343a43188"
INTEGRATED_README_SHA256 = "701d50014486960d83ad22b89c49f932e67916ecc9daeaa90bcb9e0a8385b2a8"
USAGE = "usage: check_readme_i18n.py [--release-evidence] [--help]\n"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")

CHANGED_STATUS = {
    ".github/workflows/ci.yml": "M",
    "README.md": "M",
    "README.ja.md": "A",
    "README.zh-CN.md": "A",
    "docs/i18n/source_manifest.json": "A",
    "scripts/check_readme_i18n.py": "A",
    "tests/fixtures/i18n/README.ja.visible.md": "A",
    "tests/fixtures/i18n/README.zh-CN.visible.md": "A",
    "tests/fixtures/i18n/mutation_cases.json": "A",
    "tests/test_readme_i18n.py": "A",
}
CHANGED_PATHS = list(CHANGED_STATUS)
INPUT_PATHS = CHANGED_PATHS + [
    "SECURITY.md",
    "src/agent_context_lens/__init__.py",
]
FORBIDDEN_PATHS = [
    "docs/i18n/locales.json",
    "docs/i18n/attestations",
    "docs/i18n/admissions",
    "docs/i18n/human-review",
]
FORBIDDEN_MACHINE_KEYS = [
    "attestation",
    "reviewer",
    "qualification_basis",
    "walkthrough",
    "native_review",
    "user_validation",
    "language_maintainer",
    "technical_maintainer",
    "p0_review_sla_days",
]
VALIDATION_CODES = {
    "AUTH", "BLOB", "CI", "CLAIM", "COMMAND", "DIRTY", "ENCODING",
    "FILE", "HEAVY_GATE", "HISTORY", "IA", "LINK", "META", "NAV",
    "NOTICE", "PATH", "SOURCE", "STATEMENT", "TOKEN", "VERSION",
}

VISIBLE = {
    "ja": {
        "file": "README.ja.md",
        "fixture": "tests/fixtures/i18n/README.ja.visible.md",
        "bytes": 4483,
        "lines": 78,
        "sha256": "ea1048210c7da8b83696c86d62d3b163888191d2327a3ad0a6b4fb68fbb0cda1",
        "notice": "> コミュニティ向けの非公式翻訳：このページは英語版 README より更新が遅れる場合があります。内容に相違がある場合は、英語版 README を正とします。",
        "notice_sha256": "7e9dafdb75b57de71958911c76bec0ba71c07b11cc08cb41854118717bf7283b",
        "nav": "[English](README.md) | [简体中文](README.zh-CN.md) | **日本語**",
        "headings": [
            "## Agent Context Lens とは",
            "## クイックスタート",
            "## 主な機能",
            "## 主な制約",
            "## プライバシーと安全性",
            "## フィードバックと英語版の完全なドキュメント",
        ],
    },
    "zh-CN": {
        "file": "README.zh-CN.md",
        "fixture": "tests/fixtures/i18n/README.zh-CN.visible.md",
        "bytes": 2986,
        "lines": 78,
        "sha256": "801b13f40b640a944f7cf4d7e95afe43374c0b1c4ba30dc1e7ca16468147f2bb",
        "notice": "> 面向社区的非官方翻译：本页面可能落后于英文 README。若内容存在冲突，以英文 README 为准。",
        "notice_sha256": "58d0e110b09c1579111f30aaef2f625b443126da40413ad219aa153b7c1c37cd",
        "nav": "[English](README.md) | **简体中文** | [日本語](README.ja.md)",
        "headings": [
            "## 这是什么",
            "## 快速开始",
            "## 核心能力",
            "## 核心限制",
            "## 隐私与安全",
            "## 反馈与完整英文文档",
        ],
    },
}

SOURCE_BLOCKS = {
    "intro": {
        "anchor": "acl-i18n-intro",
        "baseline_start_line": 9,
        "baseline_end_line": 17,
        "baseline_sha256": "372f069bc415ae9c46c1d074e7dbea1c3fc3e2e0a5cd9c9f73bb4006559421f9",
        "integrated_sha256": "372f069bc415ae9c46c1d074e7dbea1c3fc3e2e0a5cd9c9f73bb4006559421f9",
        "localized_section": "introduction",
    },
    "quick-start": {
        "anchor": "acl-i18n-quick-start",
        "baseline_start_line": 19,
        "baseline_end_line": 47,
        "baseline_sha256": "539072040b5f62945c925ac91367ec3a0a66349122c874298a5717bd78167dfb",
        "integrated_sha256": "9539b9f39d33414b749ae0553a619d370aa7be7412da2ec7ab02e1276d1ee50f",
        "localized_section": "quick-start",
    },
    "capabilities": {
        "anchor": "acl-i18n-capabilities",
        "baseline_start_line": 49,
        "baseline_end_line": 101,
        "baseline_sha256": "199e8527036fe57ad3826e9a668c8ac73e469802e6429c886c9c5c941160aba7",
        "integrated_sha256": "199e8527036fe57ad3826e9a668c8ac73e469802e6429c886c9c5c941160aba7",
        "localized_section": "capabilities",
    },
    "limitations": {
        "anchor": "acl-i18n-limitations",
        "baseline_start_line": 102,
        "baseline_end_line": 127,
        "baseline_sha256": "8378249895026dbd25a24b782fd69b5e2b74866f167c5534f80042665d2497d8",
        "integrated_sha256": "8378249895026dbd25a24b782fd69b5e2b74866f167c5534f80042665d2497d8",
        "localized_section": "limitations",
    },
    "privacy-safety": {
        "anchor": "acl-i18n-privacy-safety",
        "baseline_start_line": 129,
        "baseline_end_line": 139,
        "baseline_sha256": "82f51e037cec3b93e20447adc186fa92e1b461da3e0bd0559965e00fff0feb82",
        "integrated_sha256": "82f51e037cec3b93e20447adc186fa92e1b461da3e0bd0559965e00fff0feb82",
        "localized_section": "privacy-safety",
    },
    "feedback": {
        "anchor": "acl-i18n-feedback",
        "baseline_start_line": 141,
        "baseline_end_line": 267,
        "baseline_sha256": "a12d0a498cb68d2583ec0a19cbe926d8629f7221e27b1df8f8ceafe94f30d979",
        "integrated_sha256": "a12d0a498cb68d2583ec0a19cbe926d8629f7221e27b1df8f8ceafe94f30d979",
        "localized_section": "feedback",
    },
}

COMMANDS = {
    "QS-01": 'python -m pip install "git+https://github.com/ciceroyang/agent-context-lens.git"',
    "QS-02": "agent-context-lens /path/to/repository",
    "QS-03": (
        "agent-context-lens /path/to/repository \\\n"
        "  --explain --agent codex \\\n"
        "  --cwd /path/to/repository/services/payments \\\n"
        "  --project-root /path/to/repository"
    ),
}

PROTECTED_TOKENS = [
    {"id": "INTRO_PRODUCT", "token": "Agent Context Lens", "section": "intro", "localized_exact_count": 1},
    {"id": "INTRO_AGENTS", "token": "AGENTS.md", "section": "intro", "localized_exact_count": 1},
    {"id": "INTRO_CODEX", "token": "Codex", "section": "intro", "localized_exact_count": 1},
    {"id": "EVIDENCE_OFFICIAL", "token": "official_contract", "section": "capabilities", "localized_exact_count": 1},
    {"id": "EVIDENCE_VERSIONED", "token": "versioned_observation", "section": "capabilities", "localized_exact_count": 1},
    {"id": "EVIDENCE_UNKNOWN", "token": "unknown", "section": "capabilities", "localized_exact_count": 1},
    {"id": "LIMIT_UNKNOWN", "token": "unknown", "section": "limitations", "localized_exact_count": 1},
    {"id": "LIMIT_CONFIG", "token": ".codex/config.toml", "section": "limitations", "localized_exact_count": 1},
    {"id": "LIMIT_TOML_REASON", "token": "toml_config_not_parsed", "section": "limitations", "localized_exact_count": 1},
    {"id": "SAFE_INCLUDE_USER", "token": "--include-user", "section": "privacy-safety", "localized_exact_count": 1},
    {"id": "SAFE_USER_REASON", "token": "user_scope_not_requested", "section": "privacy-safety", "localized_exact_count": 1},
    {"id": "SAFE_USER_OVERRIDE", "token": "CODEX_HOME/AGENTS.override.md", "section": "privacy-safety", "localized_exact_count": 1},
    {"id": "SAFE_USER_AGENTS", "token": "CODEX_HOME/AGENTS.md", "section": "privacy-safety", "localized_exact_count": 1},
    {"id": "SAFE_CODEX_HOME", "token": "CODEX_HOME", "section": "privacy-safety", "localized_exact_count": 1},
    {"id": "FEEDBACK_SECURITY", "token": "SECURITY.md", "section": "feedback", "localized_exact_count": 1},
]

STATEMENTS = {
    "zh-CN": {
        "LIMIT-DECLARED": "声明的配置不等于未来某次 Codex 调用的实际有效配置；无法验证的版本、平台、编码和文件系统行为会保持为 `unknown` 或不支持。",
        "LIMIT-TOML": "Agent Context Lens 不解析 `.codex/config.toml`；相关有效值未声明时会显示 `toml_config_not_parsed`。",
        "SAFE-LOCAL": "工具在本地确定性运行，不调用模型，也不发起网络请求。",
        "SAFE-USER-SCOPE": "默认情况下不会打开、检查、哈希或读取 `CODEX_HOME/AGENTS.override.md` 和 `CODEX_HOME/AGENTS.md`，并报告 `user_scope_not_requested`；只有显式使用 `--include-user` 才会包含用户级指令。",
        "SAFE-SYMLINK": "在已接受的 macOS ARM64 证据范围内，安全模式会拒绝指令文件、路径目录和 `CODEX_HOME` 符号链接；其他平台的行为保持未知，因此结果不能被描述为与 Codex 完全一致或具有通用跨平台竞态安全性。",
        "SAFE-NO-CONTENT": "报告包含元数据和哈希，不包含指令正文。",
        "FEEDBACK-REDACT": "提交反馈前，请移除密钥、私有路径和专有指令。",
    },
    "ja": {
        "LIMIT-DECLARED": "宣言された設定は、将来の Codex 実行で実際に有効になる設定と同一ではありません。検証できないバージョン、プラットフォーム、文字コード、ファイルシステムの挙動は `unknown` または未サポートのままです。",
        "LIMIT-TOML": "Agent Context Lens は `.codex/config.toml` を解析しません。関連する有効値が宣言されていない場合は `toml_config_not_parsed` を表示します。",
        "SAFE-LOCAL": "本ツールはローカルかつ決定論的に動作し、モデルを呼び出さず、ネットワーク要求も行いません。",
        "SAFE-USER-SCOPE": "デフォルトでは `CODEX_HOME/AGENTS.override.md` と `CODEX_HOME/AGENTS.md` を開かず、検査、ハッシュ化、内容の読み取りも行いません。また `user_scope_not_requested` として報告します。ユーザー範囲の指示を含めるのは `--include-user` を明示した場合だけです。",
        "SAFE-SYMLINK": "受け入れ済みの macOS ARM64 証拠の範囲では、セーフモードは指示ファイル、パス上のディレクトリ、`CODEX_HOME` のシンボリックリンクを拒否します。他のプラットフォームの挙動は不明なため、結果を Codex と完全に同一、またはプラットフォームを問わず競合状態に対して安全なものとは表現できません。",
        "SAFE-NO-CONTENT": "レポートにはメタデータとハッシュが含まれ、指示本文は含まれません。",
        "FEEDBACK-REDACT": "フィードバックを共有する前に、シークレット、非公開パス、プロプライエタリな指示を削除してください。",
    },
}

FORBIDDEN_IMPLICATIONS = {
    "zh-CN": ["已审阅", "已审核", "母语审校完成", "用户验证完成", "受支持的翻译", "与英文完全一致"],
    "ja": ["レビュー済み", "承認済み", "ネイティブレビュー完了", "ユーザー検証済み", "サポート済みの翻訳", "英語版と完全に同一"],
}

ACCEPTANCE_IDS = [
    "BASE-01", "BASE-02", "BASE-03", "FILE-01", "FILE-02", "NAV-01",
    "NAV-02", "NOTICE-01", "NOTICE-02", "NOTICE-03", "IA-01", "CLAIM-01",
    "CLAIM-02", "SOURCE-01", "SOURCE-02", "SOURCE-03", "SOURCE-04",
    "META-01", "META-02", "COMMAND-01", "COMMAND-02", "TOKEN-01",
    "STATEMENT-01", "LINK-01", "LINK-02", "VERSION-01", "ENCODING-01",
    "PATH-01", "BLOB-01", "CLI-01", "CLI-02", "CLI-03", "EVIDENCE-01",
    "EVIDENCE-02", "CI-01", "CI-02", "LIGHT-01", "LIGHT-02", "LIGHT-03",
    "NONCLAIM-01", "AUTH-01",
]

WORKFLOW_NEGATIVES = [
    "fully-commented-job", "commented-fetch-depth", "commented-python-version",
    "commented-run", "unrelated-job", "wrong-indentation", "duplicate-job",
    "false-job-condition", "false-step-condition", "continue-on-error",
    "wrong-fetch-depth", "wrong-python", "masked-command",
    "jobs-plain-before", "jobs-plain-after", "jobs-anchor-before",
    "jobs-anchor-after", "jobs-quoted-before", "jobs-quoted-after",
    "jobs-tagged-before", "jobs-tagged-after", "i18n-plain-before",
    "i18n-plain-after", "i18n-anchor-before", "i18n-anchor-after",
    "i18n-quoted-before", "i18n-quoted-after", "i18n-tagged-before",
    "i18n-tagged-after", "remove-checker", "remove-test", "reverse-commands",
    "disable-checker", "disable-test", "continue-checker", "continue-test",
    "mask-checker", "mask-test",
]

PROPOSAL_JSONL = """{"baseline_commit":"e6498fbf7c1b89d368aea7fc42120357ef4bc27a","baseline_readme_bytes":8926,"baseline_readme_lines":271,"baseline_readme_sha256":"c5c3cf854731e067ab88ede40551260932a8ff4423304420c309716343a43188","line_ending":"LF","record":"header","schema_version":1}
{"baseline_bytes":547,"baseline_end_line":17,"baseline_lines":9,"baseline_sha256":"372f069bc415ae9c46c1d074e7dbea1c3fc3e2e0a5cd9c9f73bb4006559421f9","baseline_start_line":9,"id":"intro","integrated_payload_bytes":547,"integrated_payload_sha256":"372f069bc415ae9c46c1d074e7dbea1c3fc3e2e0a5cd9c9f73bb4006559421f9","localized_section":"introduction","record":"source"}
{"baseline_bytes":784,"baseline_end_line":47,"baseline_lines":29,"baseline_sha256":"539072040b5f62945c925ac91367ec3a0a66349122c874298a5717bd78167dfb","baseline_start_line":19,"id":"quick-start","integrated_payload_bytes":982,"integrated_payload_sha256":"9539b9f39d33414b749ae0553a619d370aa7be7412da2ec7ab02e1276d1ee50f","localized_section":"quick-start","record":"source"}
{"baseline_bytes":1827,"baseline_end_line":101,"baseline_lines":53,"baseline_sha256":"199e8527036fe57ad3826e9a668c8ac73e469802e6429c886c9c5c941160aba7","baseline_start_line":49,"id":"capabilities","integrated_payload_bytes":1827,"integrated_payload_sha256":"199e8527036fe57ad3826e9a668c8ac73e469802e6429c886c9c5c941160aba7","localized_section":"capabilities","record":"source"}
{"baseline_bytes":873,"baseline_end_line":127,"baseline_lines":26,"baseline_sha256":"8378249895026dbd25a24b782fd69b5e2b74866f167c5534f80042665d2497d8","baseline_start_line":102,"id":"limitations","integrated_payload_bytes":873,"integrated_payload_sha256":"8378249895026dbd25a24b782fd69b5e2b74866f167c5534f80042665d2497d8","localized_section":"limitations","record":"source"}
{"baseline_bytes":536,"baseline_end_line":139,"baseline_lines":11,"baseline_sha256":"82f51e037cec3b93e20447adc186fa92e1b461da3e0bd0559965e00fff0feb82","baseline_start_line":129,"id":"privacy-safety","integrated_payload_bytes":536,"integrated_payload_sha256":"82f51e037cec3b93e20447adc186fa92e1b461da3e0bd0559965e00fff0feb82","localized_section":"privacy-safety","record":"source"}
{"baseline_bytes":3904,"baseline_end_line":267,"baseline_lines":127,"baseline_sha256":"a12d0a498cb68d2583ec0a19cbe926d8629f7221e27b1df8f8ceafe94f30d979","baseline_start_line":141,"id":"feedback","integrated_payload_bytes":3904,"integrated_payload_sha256":"a12d0a498cb68d2583ec0a19cbe926d8629f7221e27b1df8f8ceafe94f30d979","localized_section":"feedback","record":"source"}
{"after_line":1,"id":"NAV","payload":"\\n**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)\\n","record":"insert"}
{"after_line":8,"id":"SOURCE-INTRO-OPEN","payload":"<a id=\\"acl-i18n-intro\\"></a>\\n<!-- i18n-source:start:intro -->\\n","record":"insert"}
{"after_line":17,"id":"SOURCE-INTRO-CLOSE","payload":"<!-- i18n-source:end:intro -->\\n","record":"insert"}
{"after_line":18,"id":"SOURCE-QUICK-OPEN","payload":"<a id=\\"acl-i18n-quick-start\\"></a>\\n<!-- i18n-source:start:quick-start -->\\n","record":"insert"}
{"after_line":22,"id":"COMMAND-QS-01-OPEN","payload":"<!-- i18n-command:start:QS-01 -->\\n","record":"insert"}
{"after_line":25,"id":"COMMAND-QS-01-CLOSE","payload":"<!-- i18n-command:end:QS-01 -->\\n","record":"insert"}
{"after_line":28,"id":"COMMAND-QS-02-OPEN","payload":"<!-- i18n-command:start:QS-02 -->\\n","record":"insert"}
{"after_line":31,"id":"COMMAND-QS-02-CLOSE","payload":"<!-- i18n-command:end:QS-02 -->\\n","record":"insert"}
{"after_line":34,"id":"COMMAND-QS-03-OPEN","payload":"<!-- i18n-command:start:QS-03 -->\\n","record":"insert"}
{"after_line":40,"id":"COMMAND-QS-03-CLOSE","payload":"<!-- i18n-command:end:QS-03 -->\\n","record":"insert"}
{"after_line":47,"id":"SOURCE-QUICK-CLOSE","payload":"<!-- i18n-source:end:quick-start -->\\n","record":"insert"}
{"after_line":48,"id":"SOURCE-CAPABILITIES-OPEN","payload":"<a id=\\"acl-i18n-capabilities\\"></a>\\n<!-- i18n-source:start:capabilities -->\\n","record":"insert"}
{"after_line":101,"id":"SOURCE-CAPABILITIES-CLOSE","payload":"<!-- i18n-source:end:capabilities -->\\n","record":"insert"}
{"after_line":101,"id":"SOURCE-LIMITATIONS-OPEN","payload":"<a id=\\"acl-i18n-limitations\\"></a>\\n<!-- i18n-source:start:limitations -->\\n","record":"insert"}
{"after_line":127,"id":"SOURCE-LIMITATIONS-CLOSE","payload":"<!-- i18n-source:end:limitations -->\\n","record":"insert"}
{"after_line":128,"id":"SOURCE-PRIVACY-OPEN","payload":"<a id=\\"acl-i18n-privacy-safety\\"></a>\\n<!-- i18n-source:start:privacy-safety -->\\n","record":"insert"}
{"after_line":139,"id":"SOURCE-PRIVACY-CLOSE","payload":"<!-- i18n-source:end:privacy-safety -->\\n","record":"insert"}
{"after_line":140,"id":"SOURCE-FEEDBACK-OPEN","payload":"<a id=\\"acl-i18n-feedback\\"></a>\\n<!-- i18n-source:start:feedback -->\\n","record":"insert"}
{"after_line":267,"id":"SOURCE-FEEDBACK-CLOSE","payload":"<!-- i18n-source:end:feedback -->\\n","record":"insert"}
"""


class WrongRepository(RuntimeError):
    pass


class Issues:
    def __init__(self) -> None:
        self.codes: set[str] = set()

    def add(self, code: str) -> None:
        if code not in VALIDATION_CODES:
            raise RuntimeError(f"unknown validation code: {code}")
        self.codes.add(code)

    def require(self, condition: bool, code: str) -> bool:
        if not condition:
            self.add(code)
            return False
        return True


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def initialize_repository() -> Path:
    script = Path(__file__).absolute()
    root = script.parent.parent
    if script != root / "scripts/check_readme_i18n.py":
        raise WrongRepository
    process = run_git(root, "rev-parse", "--show-toplevel")
    if process.returncode != 0:
        raise WrongRepository
    try:
        reported = Path(process.stdout.decode("utf-8", "strict").strip()).resolve()
    except (UnicodeError, OSError):
        raise WrongRepository from None
    if reported != root.resolve():
        raise WrongRepository
    return root


def safe_read(root: Path, relative: str, issues: Issues) -> bytes | None:
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        issues.add("PATH")
        return None
    root_resolved = root.resolve()
    try:
        root_stat = os.lstat(root)
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            issues.add("PATH")
            return None
        current = root
        for part in parts[:-1]:
            current = current / part
            current_stat = os.lstat(current)
            if stat.S_ISLNK(current_stat.st_mode) or not stat.S_ISDIR(current_stat.st_mode):
                issues.add("PATH")
                return None
        candidate = root.joinpath(*parts)
        candidate_stat = os.lstat(candidate)
        if stat.S_ISLNK(candidate_stat.st_mode) or not stat.S_ISREG(candidate_stat.st_mode):
            issues.add("PATH")
            return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            issues.add("PATH")
            return None
        descriptor = os.open(candidate, os.O_RDONLY | nofollow)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                issues.add("PATH")
                return None
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            os.close(descriptor)
        return b"".join(chunks)
    except FileNotFoundError:
        issues.add("FILE")
    except (OSError, RuntimeError, ValueError):
        issues.add("PATH")
    return None


def strict_text(data: bytes | None, issues: Issues) -> str | None:
    if data is None:
        return None
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data:
        issues.add("ENCODING")
        return None
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        issues.add("ENCODING")
        return None
    if not text.endswith("\n") or text.endswith("\n\n"):
        issues.add("ENCODING")
        return None
    return text


def parse_json(data: bytes | None, issues: Issues, code: str = "META") -> Any | None:
    text = strict_text(data, issues)
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeError):
        issues.add(code)
        return None


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def proposal_records(issues: Issues) -> list[dict[str, Any]]:
    raw = PROPOSAL_JSONL.encode("utf-8")
    issues.require(sha256(raw) == PROPOSAL_SHA256, "SOURCE")
    try:
        records = [json.loads(line) for line in PROPOSAL_JSONL.splitlines()]
    except json.JSONDecodeError:
        issues.add("SOURCE")
        return []
    issues.require(len(records) == 26, "SOURCE")
    return records


def apply_proposal(baseline: bytes, records: list[dict[str, Any]]) -> bytes:
    lines = baseline.splitlines(keepends=True)
    inserts: dict[int, list[bytes]] = {}
    for record in records:
        if record.get("record") == "insert":
            inserts.setdefault(int(record["after_line"]), []).append(
                record["payload"].encode("utf-8")
            )
    output: list[bytes] = []
    for number, line in enumerate(lines, 1):
        output.append(line)
        output.extend(inserts.get(number, []))
    return b"".join(output)


def reverse_proposal(integrated: bytes, records: list[dict[str, Any]], issues: Issues) -> bytes:
    result = integrated
    for record in reversed(records):
        if record.get("record") != "insert":
            continue
        payload = record["payload"].encode("utf-8")
        if result.count(payload) != 1:
            issues.add("SOURCE")
            return result
        result = result.replace(payload, b"", 1)
    return result


def source_payload(readme: bytes, block_id: str, issues: Issues) -> bytes | None:
    block = SOURCE_BLOCKS[block_id]
    opening = (
        f'<a id="{block["anchor"]}"></a>\n'
        f"<!-- i18n-source:start:{block_id} -->\n"
    ).encode()
    closing = f"<!-- i18n-source:end:{block_id} -->\n".encode()
    if readme.count(opening) != 1 or readme.count(closing) != 1:
        issues.add("SOURCE")
        return None
    start = readme.index(opening) + len(opening)
    end = readme.index(closing)
    if end <= start:
        issues.add("SOURCE")
        return None
    return readme[start:end]


def extract_commands(data: bytes, issues: Issues) -> dict[str, bytes]:
    extracted: dict[str, bytes] = {}
    previous = -1
    for command_id, payload in COMMANDS.items():
        opening = f"<!-- i18n-command:start:{command_id} -->\n".encode()
        closing = f"<!-- i18n-command:end:{command_id} -->\n".encode()
        expected = f"```bash\n{payload}\n```\n".encode()
        if data.count(opening) != 1 or data.count(closing) != 1:
            issues.add("COMMAND")
            continue
        start_marker = data.index(opening)
        start = start_marker + len(opening)
        end = data.index(closing)
        if start_marker <= previous or end <= start:
            issues.add("COMMAND")
            continue
        observed = data[start:end]
        if observed != expected:
            issues.add("COMMAND")
        extracted[command_id] = observed
        previous = end
    return extracted


def strip_localized(data: bytes, locale: str, issues: Issues) -> tuple[bytes | None, dict[str, Any] | None]:
    marker = b"<!-- i18n-light-meta\n"
    end_marker = b"-->\n"
    if data.count(marker) != 1:
        issues.add("META")
        return None, None
    start = data.index(marker)
    end = data.find(end_marker, start + len(marker))
    if end < 0:
        issues.add("META")
        return None, None
    notice = VISIBLE[locale]["notice"].encode()
    if data[:start].endswith(notice + b"\n") is False:
        issues.add("NOTICE")
    raw_json = data[start + len(marker) : end]
    try:
        metadata = json.loads(raw_json.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError):
        issues.add("META")
        metadata = None
    visible = data[:start] + data[end + len(end_marker) :]
    for command_id in COMMANDS:
        for kind in ("start", "end"):
            line = f"<!-- i18n-command:{kind}:{command_id} -->\n".encode()
            if visible.count(line) != 1:
                issues.add("COMMAND")
            visible = visible.replace(line, b"", 1)
    return visible, metadata


def expected_manifest() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "contract_id": CONTRACT_ID,
        "canonical_file": "README.md",
        "baseline_commit": BASELINE,
        "baseline_readme": {
            "bytes": 8926,
            "lines": 271,
            "sha256": BASELINE_README_SHA256,
        },
        "baseline_audit": {
            "ref": "operations/audits/ACL_V02_FINAL_EVIDENCE_REAUDIT.md",
            "sha256": "4b7a1a4996ab16cdc1da4d2f40a984172066f476d68117ded5b83ad37b16e846",
        },
        "english_patch_proposal_sha256": PROPOSAL_SHA256,
        "integrated_readme": {
            "bytes": 9844,
            "lines": 297,
            "sha256": INTEGRATED_README_SHA256,
        },
        "product_version": VERSION,
        "human_evidence_required": False,
        "changed_paths": CHANGED_PATHS,
        "locale_files": {"ja": "README.ja.md", "zh-CN": "README.zh-CN.md"},
        "visible_goldens": {
            locale: {
                "bytes": VISIBLE[locale]["bytes"],
                "file": VISIBLE[locale]["fixture"],
                "lines": VISIBLE[locale]["lines"],
                "sha256": VISIBLE[locale]["sha256"],
            }
            for locale in ("ja", "zh-CN")
        },
        "source_block_order": list(SOURCE_BLOCKS),
        "source_blocks": SOURCE_BLOCKS,
        "command_order": list(COMMANDS),
        "protected_tokens": PROTECTED_TOKENS,
        "required_statement_sha256": {
            locale: {
                statement_id: sha256(statement.encode())
                for statement_id, statement in STATEMENTS[locale].items()
            }
            for locale in ("ja", "zh-CN")
        },
        "required_notice_sha256": {
            locale: VISIBLE[locale]["notice_sha256"]
            for locale in ("ja", "zh-CN")
        },
        "required_external_links": [
            "https://github.com/ciceroyang/agent-context-lens/discussions/1",
            "https://github.com/ciceroyang/agent-context-lens/issues/new?template=missing_context_path.yml",
        ],
        "forbidden_machine_keys": FORBIDDEN_MACHINE_KEYS,
    }


def expected_metadata(locale: str, manifest_sha: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "contract_id": CONTRACT_ID,
        "locale": locale,
        "canonical_file": "README.md",
        "baseline_commit": BASELINE,
        "product_version": VERSION,
        "human_evidence_required": False,
        "english_patch_proposal_sha256": PROPOSAL_SHA256,
        "source_manifest_sha256": manifest_sha,
        "visible_golden_sha256": VISIBLE[locale]["sha256"],
        "source_blocks": {
            block_id: block["integrated_sha256"]
            for block_id, block in SOURCE_BLOCKS.items()
        },
    }


def recursive_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(str(key))
            found.update(recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(recursive_keys(child))
    return found


def section_text(text: str, headings: list[str], index: int) -> str:
    start = text.index(headings[index]) + len(headings[index])
    end = text.index(headings[index + 1]) if index + 1 < len(headings) else len(text)
    return text[start:end]


def validate_localized(
    locale: str,
    data: bytes | None,
    fixture: bytes | None,
    manifest_sha: str | None,
    issues: Issues,
) -> None:
    text = strict_text(data, issues)
    fixture_text = strict_text(fixture, issues)
    if text is None or fixture_text is None or data is None or fixture is None:
        return
    visible, metadata = strip_localized(data, locale, issues)
    if visible is None:
        return
    issues.require(len(fixture) == VISIBLE[locale]["bytes"], "CLAIM")
    issues.require(len(fixture.splitlines()) == VISIBLE[locale]["lines"], "CLAIM")
    issues.require(sha256(fixture) == VISIBLE[locale]["sha256"], "CLAIM")
    issues.require(visible == fixture, "CLAIM")
    visible_text = strict_text(visible, issues)
    if visible_text is None:
        return
    lines = visible_text.splitlines()
    issues.require(lines[:3] == ["# Agent Context Lens", "", VISIBLE[locale]["nav"]], "NAV")
    issues.require(len(lines) > 4 and lines[4] == VISIBLE[locale]["notice"], "NOTICE")
    issues.require(
        sha256(VISIBLE[locale]["notice"].encode()) == VISIBLE[locale]["notice_sha256"],
        "NOTICE",
    )
    observed_headings = [line for line in lines if line.startswith("## ")]
    issues.require(observed_headings == VISIBLE[locale]["headings"], "IA")
    issues.require(len(lines) <= 180, "IA")
    for forbidden in FORBIDDEN_IMPLICATIONS[locale]:
        issues.require(forbidden not in visible_text, "CLAIM")
    if metadata is None or manifest_sha is None:
        issues.add("META")
    else:
        issues.require(metadata == expected_metadata(locale, manifest_sha), "META")
        issues.require(
            not recursive_keys(metadata).intersection(FORBIDDEN_MACHINE_KEYS),
            "HEAVY_GATE",
        )
    locale_commands = extract_commands(data, issues)
    for command_id, payload in COMMANDS.items():
        issues.require(
            locale_commands.get(command_id)
            == f"```bash\n{payload}\n```\n".encode(),
            "COMMAND",
        )
    section_indexes = {
        "intro": 0,
        "capabilities": 2,
        "limitations": 3,
        "privacy-safety": 4,
        "feedback": 5,
    }
    for row in PROTECTED_TOKENS:
        body = section_text(visible_text, VISIBLE[locale]["headings"], section_indexes[row["section"]])
        issues.require(
            body.count(f"`{row['token']}`") == row["localized_exact_count"],
            "TOKEN",
        )
    statement_sections = {
        "LIMIT-DECLARED": 3,
        "LIMIT-TOML": 3,
        "SAFE-LOCAL": 4,
        "SAFE-USER-SCOPE": 4,
        "SAFE-SYMLINK": 4,
        "SAFE-NO-CONTENT": 4,
        "FEEDBACK-REDACT": 5,
    }
    for statement_id, statement in STATEMENTS[locale].items():
        body = section_text(visible_text, VISIBLE[locale]["headings"], statement_sections[statement_id])
        issues.require(
            visible_text.splitlines().count(statement) == 1
            and statement in body.splitlines(),
            "STATEMENT",
        )
    required_local = [
        "README.md",
        "README.md#acl-i18n-quick-start",
        "README.md#acl-i18n-limitations",
        "README.md#acl-i18n-privacy-safety",
        "README.md#acl-i18n-feedback",
        "SECURITY.md",
    ]
    for target in required_local:
        issues.require(f"]({target})" in visible_text, "LINK")
    observed_link_targets = re.findall(r"\]\(([^)\n]+)\)", visible_text)
    expected_link_targets = re.findall(r"\]\(([^)\n]+)\)", fixture_text)
    issues.require(observed_link_targets == expected_link_targets, "LINK")
    for target in expected_manifest()["required_external_links"]:
        issues.require(
            visible_text.count(target) == 1
            and bool(re.fullmatch(r"https://github\.com/[A-Za-z0-9_./?=&-]+", target)),
            "LINK",
        )
    issues.require(visible_text.count(f"`{VERSION}`") == 1, "VERSION")


def extract_literal_version(source: bytes | None, issues: Issues) -> str | None:
    if source is None:
        return None
    try:
        tree = ast.parse(source.decode("utf-8", "strict"))
    except (UnicodeError, SyntaxError):
        issues.add("VERSION")
        return None
    values: list[str] = []
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            values.append(node.value.value)
    if len(values) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", values[0]):
        issues.add("VERSION")
        return None
    return values[0]


def imported_modules(source: str, issues: Issues) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        issues.add("AUTH")
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", 1)[0])
    return modules


def validate_workflow(data: bytes | None, issues: Issues) -> None:
    text = strict_text(data, issues)
    if text is None:
        return
    lines = text.splitlines()

    def active(line: str) -> bool:
        return bool(line.strip()) and not line.lstrip().startswith("#")

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def direct_mapping_key(line: str, indent: int) -> str | None:
        if not active(line) or indent_of(line) != indent:
            return None
        match = re.fullmatch(r"([A-Za-z0-9_-]+):(?:[ \t]+.*)?", line[indent:])
        issues.require(match is not None, "CI")
        return match.group(1) if match else None

    for line in lines:
        if not active(line):
            continue
        leading = line[: len(line) - len(line.lstrip(" \t"))]
        issues.require("\t" not in leading and len(leading) % 2 == 0, "CI")
    top_level = [
        (index, line, direct_mapping_key(line, 0))
        for index, line in enumerate(lines)
        if active(line) and indent_of(line) == 0
    ]
    jobs_entries = [(index, line) for index, line, key in top_level if key == "jobs"]
    if not issues.require(
        len(jobs_entries) == 1 and jobs_entries[0][1] == "jobs:",
        "CI",
    ):
        return
    jobs_start = jobs_entries[0][0]
    jobs_end = len(lines)
    for index in range(jobs_start + 1, len(lines)):
        if active(lines[index]) and indent_of(lines[index]) == 0:
            jobs_end = index
            break
    jobs_section = lines[jobs_start + 1 : jobs_end]
    direct_jobs = [
        (index, line, direct_mapping_key(line, 2))
        for index, line in enumerate(jobs_section)
        if active(line) and indent_of(line) == 2
    ]
    i18n_entries = [(index, line) for index, line, key in direct_jobs if key == "i18n"]
    if not issues.require(
        len(i18n_entries) == 1 and i18n_entries[0][1] == "  i18n:",
        "CI",
    ):
        return
    i18n_start = i18n_entries[0][0]
    i18n_end = len(jobs_section)
    for index in range(i18n_start + 1, len(jobs_section)):
        if active(jobs_section[index]) and indent_of(jobs_section[index]) == 2:
            i18n_end = index
            break
    observed = [line for line in jobs_section[i18n_start:i18n_end] if active(line)]
    expected = [
        "  i18n:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
        "        with:",
        "          fetch-depth: 0",
        "      - uses: actions/setup-python@v5",
        "        with:",
        '          python-version: "3.10"',
        '      - run: python -m pip install "pytest>=8.0"',
        "      - run: python scripts/check_readme_i18n.py --release-evidence",
        "      - run: python -m pytest tests/test_readme_i18n.py",
    ]
    issues.require(observed == expected, "CI")


def parse_name_status(data: bytes, issues: Issues) -> dict[str, str]:
    fields = data.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        issues.add("BLOB")
        return {}
    parsed: dict[str, str] = {}
    try:
        for index in range(0, len(fields), 2):
            status_value = fields[index].decode("ascii", "strict")
            relative = fields[index + 1].decode("utf-8", "strict")
            if status_value not in {"A", "M"} or relative in parsed:
                issues.add("BLOB")
                return {}
            parsed[relative] = status_value
    except UnicodeError:
        issues.add("BLOB")
        return {}
    return parsed


def validate_release(
    root: Path,
    files: dict[str, bytes | None],
    readme: bytes | None,
    records: list[dict[str, Any]],
    issues: Issues,
    proof: dict[str, Any],
) -> None:
    shallow = run_git(root, "rev-parse", "--is-shallow-repository")
    issues.require(shallow.returncode == 0 and shallow.stdout == b"false\n", "HISTORY")
    baseline_type = run_git(root, "cat-file", "-t", BASELINE)
    issues.require(
        baseline_type.returncode == 0 and baseline_type.stdout == b"commit\n",
        "HISTORY",
    )
    head_process = run_git(root, "rev-parse", "HEAD")
    if head_process.returncode == 0:
        try:
            head = head_process.stdout.decode("ascii", "strict").strip()
        except UnicodeError:
            head = ""
        if COMMIT_RE.fullmatch(head):
            proof["checked_commit"] = head
        else:
            issues.add("HISTORY")
    else:
        issues.add("HISTORY")
    if proof["checked_commit"] is not None:
        ancestor = run_git(root, "merge-base", "--is-ancestor", BASELINE, proof["checked_commit"])
        issues.require(ancestor.returncode == 0, "HISTORY")
    status_process = run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
    issues.require(status_process.returncode == 0 and status_process.stdout == b"", "DIRTY")
    diff_process = run_git(
        root,
        "-c",
        "core.quotepath=false",
        "diff",
        "--name-status",
        "-z",
        "--no-renames",
        BASELINE,
        "HEAD",
        "--",
    )
    if diff_process.returncode != 0:
        issues.add("BLOB")
    else:
        observed_status = parse_name_status(diff_process.stdout, issues)
        expected_rows = [
            (relative, CHANGED_STATUS[relative])
            for relative in sorted(CHANGED_STATUS, key=lambda value: value.encode("utf-8"))
        ]
        issues.require(observed_status == CHANGED_STATUS, "BLOB")
        issues.require(list(observed_status.items()) == expected_rows, "BLOB")
    for relative in INPUT_PATHS:
        tree = run_git(root, "ls-tree", "-z", "HEAD", "--", relative)
        if tree.returncode != 0 or not tree.stdout.endswith(b"\0"):
            issues.add("BLOB")
            continue
        header, separator, path_bytes = tree.stdout[:-1].partition(b"\t")
        fields = header.split()
        if separator != b"\t" or len(fields) != 3:
            issues.add("BLOB")
            continue
        mode, kind, _object_id = fields
        issues.require(mode in {b"100644", b"100755"} and kind == b"blob", "BLOB")
        issues.require(path_bytes.decode("utf-8", "replace") == relative, "BLOB")
        committed = run_git(root, "show", f"HEAD:{relative}")
        issues.require(
            committed.returncode == 0
            and files.get(relative) is not None
            and committed.stdout == files[relative],
            "BLOB",
        )
    baseline_readme = run_git(root, "show", f"{BASELINE}:README.md")
    if baseline_readme.returncode != 0:
        issues.add("HISTORY")
    else:
        baseline = baseline_readme.stdout
        issues.require(
            len(baseline) == 8926
            and len(baseline.splitlines()) == 271
            and sha256(baseline) == BASELINE_README_SHA256,
            "SOURCE",
        )
        for block_id, block in SOURCE_BLOCKS.items():
            lines = baseline.splitlines(keepends=True)
            span = b"".join(lines[block["baseline_start_line"] - 1 : block["baseline_end_line"]])
            issues.require(sha256(span) == block["baseline_sha256"], "SOURCE")
        if readme is not None:
            issues.require(apply_proposal(baseline, records) == readme, "SOURCE")
            issues.require(reverse_proposal(readme, records, issues) == baseline, "SOURCE")
    baseline_version = run_git(root, "show", f"{BASELINE}:src/agent_context_lens/__init__.py")
    issues.require(
        baseline_version.returncode == 0
        and extract_literal_version(baseline_version.stdout, issues) == VERSION,
        "VERSION",
    )


def validate_repository(root: Path, *, release_evidence: bool = False) -> dict[str, Any]:
    issues = Issues()
    mode = "release-evidence" if release_evidence else "development"
    proof: dict[str, Any] = {
        "baseline_commit": BASELINE,
        "checked_commit": None,
        "contract_id": CONTRACT_ID,
        "error_codes": [],
        "human_evidence_required": False,
        "locales": ["ja", "zh-CN"],
        "mode": mode,
        "product_version": VERSION,
        "result": "fail",
        "schema_version": 2,
        "source_manifest_sha256": None,
    }
    files = {relative: safe_read(root, relative, issues) for relative in INPUT_PATHS}
    for forbidden in FORBIDDEN_PATHS:
        issues.require(not (root / forbidden).exists() and not (root / forbidden).is_symlink(), "HEAVY_GATE")
    allowed_readmes = {"README.md", "README.ja.md", "README.zh-CN.md"}
    try:
        observed_readmes = {path.name for path in root.glob("README*.md")}
        issues.require(observed_readmes == allowed_readmes, "FILE")
        docs_files = {
            path.relative_to(root).as_posix()
            for path in (root / "docs/i18n").rglob("*")
            if path.is_file() or path.is_symlink()
        }
        fixture_files = {
            path.relative_to(root).as_posix()
            for path in (root / "tests/fixtures/i18n").rglob("*")
            if path.is_file() or path.is_symlink()
        }
        issues.require(
            docs_files == {"docs/i18n/source_manifest.json"},
            "FILE",
        )
        issues.require(
            fixture_files
            == {
                "tests/fixtures/i18n/README.ja.visible.md",
                "tests/fixtures/i18n/README.zh-CN.visible.md",
                "tests/fixtures/i18n/mutation_cases.json",
            },
            "FILE",
        )
    except OSError:
        issues.add("FILE")

    manifest_raw = files["docs/i18n/source_manifest.json"]
    if manifest_raw is not None:
        proof["source_manifest_sha256"] = sha256(manifest_raw)
    manifest = parse_json(manifest_raw, issues)
    if manifest is not None:
        issues.require(manifest == expected_manifest(), "META")
        issues.require(
            not recursive_keys(manifest).intersection(FORBIDDEN_MACHINE_KEYS),
            "HEAVY_GATE",
        )
        issues.require(json_bytes(manifest) == manifest_raw, "META")

    mutation = parse_json(files["tests/fixtures/i18n/mutation_cases.json"], issues)
    expected_mutation = {
        "schema_version": 2,
        "contract_id": CONTRACT_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "workflow_negative_cases": WORKFLOW_NEGATIVES,
        "workflow_negative_count": 38,
        "human_evidence_required": False,
    }
    if mutation is not None:
        issues.require(mutation == expected_mutation, "AUTH")
        issues.require(
            not recursive_keys(mutation).intersection(FORBIDDEN_MACHINE_KEYS),
            "HEAVY_GATE",
        )

    readme = files["README.md"]
    readme_text = strict_text(readme, issues)
    records = proposal_records(issues)
    if readme is not None and readme_text is not None:
        issues.require(
            len(readme) == 9844
            and len(readme.splitlines()) == 297
            and sha256(readme) == INTEGRATED_README_SHA256,
            "SOURCE",
        )
        issues.require(
            readme_text.splitlines()[:3]
            == [
                "# Agent Context Lens",
                "",
                "**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)",
            ],
            "NAV",
        )
        positions: list[int] = []
        for block_id, block in SOURCE_BLOCKS.items():
            payload = source_payload(readme, block_id, issues)
            if payload is not None:
                issues.require(sha256(payload) == block["integrated_sha256"], "SOURCE")
            positions.append(readme_text.find(f'<a id="{block["anchor"]}"></a>'))
        issues.require(positions == sorted(positions) and min(positions, default=-1) >= 0, "SOURCE")
        english_commands = extract_commands(readme, issues)
        issues.require(set(english_commands) == set(COMMANDS), "COMMAND")
        for locale in VISIBLE:
            locale_commands = extract_commands(files[VISIBLE[locale]["file"]] or b"", issues)
            issues.require(locale_commands == english_commands, "COMMAND")
        for block in SOURCE_BLOCKS.values():
            issues.require(
                f'<a id="{block["anchor"]}"></a>' in readme_text,
                "LINK",
            )

    for locale in ("ja", "zh-CN"):
        validate_localized(
            locale,
            files[VISIBLE[locale]["file"]],
            files[VISIBLE[locale]["fixture"]],
            proof["source_manifest_sha256"],
            issues,
        )

    version = extract_literal_version(files["src/agent_context_lens/__init__.py"], issues)
    issues.require(version == VERSION, "VERSION")
    if manifest is not None:
        issues.require(manifest.get("product_version") == VERSION, "VERSION")

    validate_workflow(files[".github/workflows/ci.yml"], issues)
    checker_source = strict_text(files["scripts/check_readme_i18n.py"], issues)
    if checker_source is not None:
        modules = imported_modules(checker_source, issues)
        issues.require(
            not modules.intersection(
                {"agent_context_lens", "urllib", "socket", "requests", "http", "ftplib"}
            ),
            "AUTH",
        )
    if release_evidence:
        validate_release(root, files, readme, records, issues, proof)

    proof["error_codes"] = sorted(issues.codes)
    proof["result"] = "pass" if not issues.codes else "fail"
    return proof


def emit_validation(proof: dict[str, Any]) -> int:
    sys.stdout.write(
        json.dumps(
            proof,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    for code in proof["error_codes"]:
        sys.stderr.write(f"ERROR {code}\n")
    return 0 if proof["result"] == "pass" else 1


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--help"]:
        sys.stdout.write(USAGE)
        return 0
    if arguments not in ([], ["--release-evidence"]):
        sys.stderr.write("ERROR CLI invalid arguments\n")
        sys.stderr.write(USAGE)
        return 2
    try:
        root = initialize_repository()
    except WrongRepository:
        sys.stderr.write("ERROR REPO wrong repository context\n")
        return 2
    except Exception:
        sys.stderr.write("ERROR STARTUP checker initialization failed\n")
        return 2
    proof = validate_repository(
        root,
        release_evidence=arguments == ["--release-evidence"],
    )
    return emit_validation(proof)


if __name__ == "__main__":
    raise SystemExit(main())

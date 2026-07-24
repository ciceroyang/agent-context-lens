from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

MAX_CONTEXT_BYTES = 1_000_000
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}

ROOT_INSTRUCTION_FILES = {
    "AGENTS.override.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".github/copilot-instructions.md",
}
MCP_CONFIG_FILES = {
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
}
VERIFICATION_PATTERN = re.compile(
    r"\b(pytest|npm\s+test|pnpm\s+test|yarn\s+test|cargo\s+test|"
    r"go\s+test|make\s+test|test\s+command|verification|verify)\b",
    re.IGNORECASE,
)
SECRET_PATTERN = re.compile(
    r"""(?ix)
    ["']?(api[_-]?key|access[_-]?token|secret|password)["']?
    \s*[:=]\s*
    ["'](?!\$\{|\{\{|<|your[_-])[A-Za-z0-9_\-./+=]{8,}["']
    """
)
RISKY_SHELL_PATTERN = re.compile(
    r"\b(bash|sh|zsh)\s+-c\b|--dangerously|--allow-all|--no-sandbox",
    re.IGNORECASE,
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class ContextFile:
    path: str
    category: str
    bytes: int
    lines: int
    approx_tokens: int
    sha256: str


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class Report:
    root: str
    score: int
    files: tuple[ContextFile, ...]
    findings: tuple[Finding, ...]
    total_bytes: int
    total_approx_tokens: int
    duplicate_line_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "root": self.root,
            "score": self.score,
            "summary": {
                "files": len(self.files),
                "total_bytes": self.total_bytes,
                "total_approx_tokens": self.total_approx_tokens,
                "duplicate_line_ratio": round(self.duplicate_line_ratio, 4),
                "critical": sum(
                    finding.severity == "critical" for finding in self.findings
                ),
                "warnings": sum(
                    finding.severity == "warning" for finding in self.findings
                ),
                "notices": sum(
                    finding.severity == "notice" for finding in self.findings
                ),
            },
            "files": [asdict(context_file) for context_file in self.files],
            "findings": [asdict(finding) for finding in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            "# Agent Context Lens report",
            "",
            f"**Score:** {self.score}/100",
            "",
            (
                f"Scanned {len(self.files)} context files, "
                f"approximately {self.total_approx_tokens:,} tokens."
            ),
            "",
            "## Findings",
            "",
        ]
        if not self.findings:
            lines.append("No findings.")
        else:
            for finding in self.findings:
                location = f" — `{finding.path}`" if finding.path else ""
                lines.append(
                    f"- **{finding.severity.upper()} {finding.code}**: "
                    f"{finding.message}{location}"
                )

        lines.extend(["", "## Context map", ""])
        if not self.files:
            lines.append("No recognized agent-context files found.")
        else:
            lines.extend(
                [
                    "| File | Category | Approx. tokens | Bytes |",
                    "|---|---:|---:|---:|",
                ]
            )
            for context_file in self.files:
                lines.append(
                    f"| `{context_file.path}` | {context_file.category} | "
                    f"{context_file.approx_tokens:,} | {context_file.bytes:,} |"
                )
        return "\n".join(lines) + "\n"

    def to_terminal(self) -> str:
        critical = sum(
            finding.severity == "critical" for finding in self.findings
        )
        warnings = sum(
            finding.severity == "warning" for finding in self.findings
        )
        file_label = "file" if len(self.files) == 1 else "files"
        lines = [
            "Agent Context Lens",
            f"Score: {self.score}/100",
            (
                f"Context: {len(self.files)} {file_label} · "
                f"~{self.total_approx_tokens:,} tokens · "
                f"{self.duplicate_line_ratio:.0%} duplicate instruction lines"
            ),
            f"Findings: {critical} critical · {warnings} warnings",
        ]
        if self.findings:
            lines.append("")
            for finding in self.findings:
                location = f" [{finding.path}]" if finding.path else ""
                lines.append(
                    f"{finding.severity.upper():8} {finding.code} "
                    f"{finding.message}{location}"
                )
        return "\n".join(lines)


def _category(relative_path: str) -> str | None:
    if relative_path in MCP_CONFIG_FILES:
        return "mcp"
    if relative_path in ROOT_INSTRUCTION_FILES:
        return "instructions"
    if (
        relative_path.endswith("/AGENTS.override.md")
        or relative_path.endswith("/AGENTS.md")
        or relative_path.endswith("/CLAUDE.md")
    ):
        return "instructions"
    if relative_path.endswith("/SKILL.md") or relative_path == "SKILL.md":
        return "skill"
    if relative_path.startswith(".cursor/rules/") and relative_path.endswith(
        (".md", ".mdc")
    ):
        return "rules"
    if relative_path.startswith(".windsurf/rules/") and relative_path.endswith(
        (".md", ".mdc")
    ):
        return "rules"
    return None


def _iter_recognized_files(root: Path) -> Iterable[tuple[Path, str]]:
    for current_root, directories, filenames in os.walk(root):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES
        )
        for filename in sorted(filenames):
            path = Path(current_root, filename)
            try:
                relative_path = path.relative_to(root).as_posix()
            except ValueError:
                continue
            category = _category(relative_path)
            if category is not None and not path.is_symlink():
                yield path, category


def _approx_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def _normalized_instruction_lines(text: str) -> list[str]:
    normalized: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lower()
        line = re.sub(r"^[-*+\d.)\s]+", "", line)
        line = re.sub(r"\s+", " ", line)
        if len(line) >= 24 and not line.startswith(("#", "```", "|---")):
            normalized.append(line)
    return normalized


def _duplicate_ratio(texts: Iterable[str]) -> float:
    lines: list[str] = []
    for text in texts:
        lines.extend(_normalized_instruction_lines(text))
    if not lines:
        return 0.0
    return (len(lines) - len(set(lines))) / len(lines)


def _broken_links(root: Path, path: Path, text: str) -> Iterable[Finding]:
    for target in MARKDOWN_LINK_PATTERN.findall(text):
        clean_target = target.strip().split("#", 1)[0]
        if (
            not clean_target
            or "://" in clean_target
            or clean_target.startswith(("mailto:", "#", "<"))
        ):
            continue
        candidate = (path.parent / clean_target).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if not candidate.exists():
            yield Finding(
                "warning",
                "CTX006",
                f"Local Markdown link points to a missing path: {clean_target}",
                path.relative_to(root).as_posix(),
            )


def scan(root: str | Path = ".") -> Report:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError(f"Not a directory: {root_path}")

    files: list[ContextFile] = []
    findings: list[Finding] = []
    content_by_path: dict[str, str] = {}

    for path, category in _iter_recognized_files(root_path):
        relative_path = path.relative_to(root_path).as_posix()
        size = path.stat().st_size
        if size > MAX_CONTEXT_BYTES:
            findings.append(
                Finding(
                    "warning",
                    "CTX002",
                    f"Context file exceeds {MAX_CONTEXT_BYTES:,} bytes and was skipped.",
                    relative_path,
                )
            )
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        content_by_path[relative_path] = text
        files.append(
            ContextFile(
                path=relative_path,
                category=category,
                bytes=size,
                lines=len(text.splitlines()),
                approx_tokens=_approx_tokens(text),
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )

        if category == "mcp":
            if SECRET_PATTERN.search(text):
                findings.append(
                    Finding(
                        "critical",
                        "SEC001",
                        "Possible inline secret in MCP configuration.",
                        relative_path,
                    )
                )
            if RISKY_SHELL_PATTERN.search(text):
                findings.append(
                    Finding(
                        "warning",
                        "SEC002",
                        "MCP command enables a broad shell or dangerous mode.",
                        relative_path,
                    )
                )

        if category != "mcp":
            findings.extend(_broken_links(root_path, path, text))

    files.sort(key=lambda item: item.path)

    if not any(context_file.path in ROOT_INSTRUCTION_FILES for context_file in files):
        findings.append(
            Finding(
                "warning",
                "CTX001",
                "No repository-level coding-agent instruction file found.",
            )
        )

    total_tokens = sum(context_file.approx_tokens for context_file in files)
    total_bytes = sum(context_file.bytes for context_file in files)
    instruction_texts = [
        content_by_path[context_file.path]
        for context_file in files
        if context_file.category != "mcp"
    ]
    duplicate_ratio = _duplicate_ratio(instruction_texts)

    if total_tokens > 12_000:
        findings.append(
            Finding(
                "warning",
                "CTX003",
                "Agent context is larger than 12,000 approximate tokens.",
            )
        )
    elif total_tokens > 6_000:
        findings.append(
            Finding(
                "notice",
                "CTX003",
                "Agent context is larger than 6,000 approximate tokens.",
            )
        )

    for context_file in files:
        if context_file.category != "mcp" and context_file.approx_tokens > 4_000:
            findings.append(
                Finding(
                    "warning",
                    "CTX004",
                    "Single context file exceeds 4,000 approximate tokens.",
                    context_file.path,
                )
            )

    if duplicate_ratio >= 0.30:
        findings.append(
            Finding(
                "warning",
                "CTX005",
                f"{duplicate_ratio:.0%} of substantial instruction lines are duplicates.",
            )
        )
    elif duplicate_ratio >= 0.15:
        findings.append(
            Finding(
                "notice",
                "CTX005",
                f"{duplicate_ratio:.0%} of substantial instruction lines are duplicates.",
            )
        )

    combined_instructions = "\n".join(instruction_texts)
    if instruction_texts and not VERIFICATION_PATTERN.search(combined_instructions):
        findings.append(
            Finding(
                "warning",
                "VER001",
                "Instructions do not name a concrete verification or test command.",
            )
        )

    severity_order = {"critical": 0, "warning": 1, "notice": 2}
    findings.sort(
        key=lambda item: (
            severity_order[item.severity],
            item.code,
            item.path or "",
        )
    )
    score = max(
        0,
        100
        - 25 * sum(item.severity == "critical" for item in findings)
        - 8 * sum(item.severity == "warning" for item in findings)
        - 2 * sum(item.severity == "notice" for item in findings),
    )

    return Report(
        root=str(root_path),
        score=score,
        files=tuple(files),
        findings=tuple(findings),
        total_bytes=total_bytes,
        total_approx_tokens=total_tokens,
        duplicate_line_ratio=duplicate_ratio,
    )

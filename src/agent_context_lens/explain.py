from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .config_snapshot import ExplainConfig


@dataclass(frozen=True)
class InstructionScope:
    scope: str
    status: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    display_path: str
    scope: str
    directory: str | None
    candidate_kind: str
    order: int | None
    state: str
    reason_codes: tuple[str, ...]
    evidence_class: str
    source_bytes: int | None
    loaded_bytes: int | None
    rendered_utf8_bytes: int | None
    separator_bytes_before: int | None
    partial: bool | None
    sha256_source: str | None
    sha256_loaded: str | None
    encoding_status: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


@dataclass(frozen=True)
class Limitation:
    code: str
    message: str
    source_id: str | None = None
    affects_parity: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextExplainReport:
    resolution_status: str
    agent: str
    root: str
    working_directory: str
    platform: str
    codex_version: str
    behavior_profile: str
    instruction_scopes: tuple[InstructionScope, ...]
    configuration: ExplainConfig
    sources: tuple[SourceRecord, ...]
    limitations: tuple[Limitation, ...]

    @property
    def has_limitations(self) -> bool:
        return bool(self.limitations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "report_type": "context_explain",
            "resolution_status": self.resolution_status,
            "agent": self.agent,
            "root": self.root,
            "working_directory": self.working_directory,
            "platform": self.platform,
            "codex_version": self.codex_version,
            "behavior_profile": self.behavior_profile,
            "instruction_scopes": [
                scope.to_dict() for scope in self.instruction_scopes
            ],
            "configuration": self.configuration.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
            "limitations": [
                limitation.to_dict() for limitation in self.limitations
            ],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
        )

    def to_terminal(self) -> str:
        lines = [
            "Agent Context Lens · explain",
            f"Status: {self.resolution_status}",
            f"Agent: {self.agent}",
            f"Project root: {self.root}",
            f"Working directory: {self.working_directory}",
            f"Platform: {self.platform}",
            f"Codex version: {self.codex_version}",
            f"Behavior profile: {self.behavior_profile}",
            "",
            "Instruction scopes",
        ]
        for scope in self.instruction_scopes:
            reasons = ", ".join(scope.reason_codes) or "none"
            lines.append(
                f"- {scope.scope}: {scope.status} · reasons={reasons}"
            )

        lines.extend(["", "Sources"])
        if not self.sources:
            lines.append("- none")
        for source in self.sources:
            reasons = ", ".join(source.reason_codes) or "none"
            lines.extend(
                [
                    (
                        f"- {source.display_path} · scope={source.scope} · "
                        f"kind={source.candidate_kind} · state={source.state} · "
                        f"order={_display(source.order)}"
                    ),
                    (
                        f"  evidence={source.evidence_class} · reasons={reasons}"
                    ),
                    (
                        f"  source_bytes={_display(source.source_bytes)} · "
                        f"loaded_bytes={_display(source.loaded_bytes)} · "
                        "rendered_utf8_bytes="
                        f"{_display(source.rendered_utf8_bytes)} · "
                        "separator_bytes_before="
                        f"{_display(source.separator_bytes_before)} · "
                        f"partial={_display(source.partial)}"
                    ),
                    (
                        f"  sha256_source={_display(source.sha256_source)} · "
                        f"sha256_loaded={_display(source.sha256_loaded)} · "
                        f"encoding={source.encoding_status}"
                    ),
                ]
            )

        lines.extend(["", "Configuration"])
        lines.extend(
            [
                f"- source: {self.configuration.source}",
                (
                    "- project_doc_max_bytes: "
                    f"{self.configuration.project_doc_max_bytes}"
                ),
                (
                    "- project_root_markers: "
                    + (
                        ", ".join(self.configuration.project_root_markers)
                        or "none"
                    )
                ),
                (
                    "- fallback_filenames: "
                    + (
                        ", ".join(self.configuration.fallback_filenames)
                        or "none"
                    )
                ),
                f"- project_trust: {self.configuration.project_trust}",
            ]
        )
        for layer in self.configuration.layers:
            if layer.status not in {"resolved", "not_present"}:
                lines.append(f"- layer {layer.kind}: {layer.status}")

        lines.extend(["", "Limitations"])
        if not self.limitations:
            lines.append("- none")
        else:
            for limitation in self.limitations:
                source = (
                    f" · source={limitation.source_id}"
                    if limitation.source_id
                    else ""
                )
                lines.append(
                    f"- {limitation.code}: {limitation.message}{source}"
                )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            "# Agent Context Lens context explanation",
            "",
            f"- **Status:** `{self.resolution_status}`",
            f"- **Agent:** `{self.agent}`",
            f"- **Project root:** `{self.root}`",
            f"- **Working directory:** `{self.working_directory}`",
            f"- **Platform:** `{self.platform}`",
            f"- **Codex version:** `{self.codex_version}`",
            f"- **Behavior profile:** `{self.behavior_profile}`",
            "",
            "## Instruction scopes",
            "",
            "| Scope | Status | Reason codes |",
            "|---|---|---|",
        ]
        for scope in self.instruction_scopes:
            reasons = ", ".join(f"`{code}`" for code in scope.reason_codes)
            lines.append(
                f"| `{scope.scope}` | `{scope.status}` | {reasons or 'none'} |"
            )

        lines.extend(
            [
                "",
                "## Sources",
                "",
            ]
        )
        if not self.sources:
            lines.append("No recognized instruction sources.")
        else:
            lines.extend(
                [
                    (
                        "| Path | Scope | Kind | State | Order | Evidence | "
                        "Reasons | Source bytes | Loaded bytes | Rendered UTF-8 "
                        "bytes | Separator bytes | Partial | Source SHA-256 | "
                        "Loaded SHA-256 | Encoding |"
                    ),
                    (
                        "|---|---|---|---|---:|---|---|---:|---:|---:|---:|"
                        "---|---|---|---|"
                    ),
                ]
            )
            for source in self.sources:
                reasons = ", ".join(
                    f"`{code}`" for code in source.reason_codes
                )
                lines.append(
                    f"| `{source.display_path}` | `{source.scope}` | "
                    f"`{source.candidate_kind}` | `{source.state}` | "
                    f"{_display(source.order)} | `{source.evidence_class}` | "
                    f"{reasons or 'none'} | {_display(source.source_bytes)} | "
                    f"{_display(source.loaded_bytes)} | "
                    f"{_display(source.rendered_utf8_bytes)} | "
                    f"{_display(source.separator_bytes_before)} | "
                    f"{_display(source.partial)} | "
                    f"`{_display(source.sha256_source)}` | "
                    f"`{_display(source.sha256_loaded)}` | "
                    f"`{source.encoding_status}` |"
                )

        lines.extend(
            [
                "",
                "## Configuration",
                "",
                f"- Source: `{self.configuration.source}`",
                (
                    "- Project byte limit: "
                    f"`{self.configuration.project_doc_max_bytes}`"
                ),
                (
                    "- Root markers: "
                    + (
                        ", ".join(
                            f"`{name}`"
                            for name in self.configuration.project_root_markers
                        )
                        or "none"
                    )
                ),
                (
                    "- Fallback filenames: "
                    + (
                        ", ".join(
                            f"`{name}`"
                            for name in self.configuration.fallback_filenames
                        )
                        or "none"
                    )
                ),
                f"- Project trust: `{self.configuration.project_trust}`",
            ]
        )
        for layer in self.configuration.layers:
            if layer.status not in {"resolved", "not_present"}:
                lines.append(f"- Layer `{layer.kind}`: `{layer.status}`")

        lines.extend(["", "## Limitations", ""])
        if not self.limitations:
            lines.append("No modeled limitations.")
        else:
            for limitation in self.limitations:
                source = (
                    f" (`{limitation.source_id}`)"
                    if limitation.source_id
                    else ""
                )
                lines.append(
                    f"- **`{limitation.code}`**: {limitation.message}{source}"
                )
        return "\n".join(lines) + "\n"


def _display(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

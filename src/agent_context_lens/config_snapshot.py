from __future__ import annotations

import json
import os
import platform as platform_module
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


LAYER_KINDS = (
    "cli_override",
    "trusted_project",
    "selected_profile",
    "user",
    "system",
    "defaults",
)
LAYER_STATUSES = {
    "resolved",
    "not_present",
    "ignored_untrusted",
    "not_inspected",
    "unknown",
}
PROJECT_TRUST_VALUES = {"trusted", "untrusted", "unknown"}
DEFAULT_ROOT_MARKERS = (".git",)
DEFAULT_PROJECT_DOC_MAX_BYTES = 32768


@dataclass(frozen=True)
class ConfigLayer:
    kind: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "status": self.status}


@dataclass(frozen=True)
class ExplainConfig:
    source: str
    project_root: str | None
    project_root_markers: tuple[str, ...]
    root_markers_declared: bool
    fallback_filenames: tuple[str, ...]
    project_doc_max_bytes: int
    project_trust: str
    codex_version: str
    behavior_profile: str
    platform: str
    selected_profile: str | None
    layers: tuple[ConfigLayer, ...]
    direct_overrides: tuple[str, ...]

    def layer_status(self, kind: str) -> str:
        for layer in self.layers:
            if layer.kind == kind:
                return layer.status
        raise KeyError(kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "selected_profile": self.selected_profile,
            "project_trust": self.project_trust,
            "project_root_markers": list(self.project_root_markers),
            "fallback_filenames": list(self.fallback_filenames),
            "project_doc_max_bytes": self.project_doc_max_bytes,
            "layers": [layer.to_dict() for layer in self.layers],
            "direct_overrides": list(self.direct_overrides),
        }


def current_platform() -> str:
    if sys.platform == "darwin":
        system = "darwin"
    elif sys.platform.startswith("linux"):
        system = "linux"
    elif sys.platform == "win32":
        system = "windows"
    else:
        system = sys.platform.replace("_", "-")

    machine = platform_module.machine().lower()
    aliases = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "amd64": "x64",
        "x86_64": "x64",
    }
    return f"{system}-{aliases.get(machine, machine)}"


def _validate_names(values: Sequence[Any], field: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must contain non-empty strings")
        if (
            value in {".", ".."}
            or os.path.isabs(value)
            or "/" in value
            or "\\" in value
        ):
            raise ValueError(f"{field} entries must be single safe names: {value}")
        if value not in result:
            result.append(value)
    return tuple(result)


def _parse_layers(value: Any) -> tuple[ConfigLayer, ...]:
    if not isinstance(value, list):
        raise ValueError("config snapshot layers must be an array")
    by_kind: dict[str, ConfigLayer] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"kind", "status"}:
            raise ValueError(
                "each config layer must contain exactly kind and status"
            )
        kind = item["kind"]
        status = item["status"]
        if kind not in LAYER_KINDS:
            raise ValueError(f"unsupported config layer kind: {kind}")
        if status not in LAYER_STATUSES:
            raise ValueError(f"unsupported config layer status: {status}")
        if kind in by_kind:
            raise ValueError(f"duplicate config layer: {kind}")
        by_kind[kind] = ConfigLayer(kind, status)
    missing = [kind for kind in LAYER_KINDS if kind not in by_kind]
    if missing:
        raise ValueError(f"config snapshot is missing layers: {', '.join(missing)}")
    return tuple(by_kind[kind] for kind in LAYER_KINDS)


def _default_layers() -> tuple[ConfigLayer, ...]:
    statuses = {
        "cli_override": "unknown",
        "trusted_project": "unknown",
        "selected_profile": "not_present",
        "user": "not_inspected",
        "system": "unknown",
        "defaults": "resolved",
    }
    return tuple(ConfigLayer(kind, statuses[kind]) for kind in LAYER_KINDS)


def _load_snapshot(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid config snapshot: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("config snapshot must be a JSON object")
    allowed = {
        "schema_version",
        "codex_version",
        "behavior_profile",
        "platform",
        "selected_profile",
        "project_trust",
        "effective",
        "layers",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(
            f"unsupported config snapshot fields: {', '.join(unknown)}"
        )
    if payload.get("schema_version") != 1:
        raise ValueError("config snapshot schema_version must be 1")
    return payload


def build_explain_config(
    *,
    snapshot_path: Path | None = None,
    project_root: str | None = None,
    root_markers: Sequence[str] | None = None,
    fallback_names: Sequence[str] | None = None,
    max_bytes: int | None = None,
    project_trust: str | None = None,
    codex_version: str | None = None,
    behavior_profile: str | None = None,
    platform: str | None = None,
) -> ExplainConfig:
    snapshot: Mapping[str, Any] = {}
    if snapshot_path is not None:
        snapshot = _load_snapshot(snapshot_path)

    effective = snapshot.get("effective", {})
    if not isinstance(effective, dict):
        raise ValueError("config snapshot effective must be an object")
    effective_allowed = {
        "project_root",
        "project_root_markers",
        "project_doc_fallback_filenames",
        "project_doc_max_bytes",
    }
    effective_unknown = sorted(set(effective) - effective_allowed)
    if effective_unknown:
        raise ValueError(
            "unsupported effective config fields: "
            + ", ".join(effective_unknown)
        )

    snapshot_root = effective.get("project_root")
    if snapshot_root is not None and not isinstance(snapshot_root, str):
        raise ValueError("effective.project_root must be a string or null")

    snapshot_markers = effective.get("project_root_markers")
    if snapshot_markers is None:
        parsed_snapshot_markers: tuple[str, ...] | None = None
    elif isinstance(snapshot_markers, list):
        parsed_snapshot_markers = _validate_names(
            snapshot_markers, "project_root_markers"
        )
    else:
        raise ValueError("effective.project_root_markers must be an array")

    snapshot_fallbacks = effective.get("project_doc_fallback_filenames", [])
    if not isinstance(snapshot_fallbacks, list):
        raise ValueError(
            "effective.project_doc_fallback_filenames must be an array"
        )
    parsed_snapshot_fallbacks = _validate_names(
        snapshot_fallbacks, "project_doc_fallback_filenames"
    )

    snapshot_max = effective.get(
        "project_doc_max_bytes", DEFAULT_PROJECT_DOC_MAX_BYTES
    )
    if (
        isinstance(snapshot_max, bool)
        or not isinstance(snapshot_max, int)
        or snapshot_max < 0
    ):
        raise ValueError(
            "effective.project_doc_max_bytes must be a non-negative integer"
        )

    snapshot_trust = snapshot.get("project_trust", "unknown")
    if snapshot_trust not in PROJECT_TRUST_VALUES:
        raise ValueError(f"unsupported project_trust: {snapshot_trust}")

    snapshot_codex_version = snapshot.get("codex_version", "unknown")
    snapshot_behavior_profile = snapshot.get(
        "behavior_profile", "official-contract"
    )
    snapshot_platform = snapshot.get("platform", current_platform())
    snapshot_selected_profile = snapshot.get("selected_profile")
    for field, value in (
        ("codex_version", snapshot_codex_version),
        ("behavior_profile", snapshot_behavior_profile),
        ("platform", snapshot_platform),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be a non-empty string")
    if snapshot_selected_profile is not None and (
        not isinstance(snapshot_selected_profile, str)
        or not snapshot_selected_profile
    ):
        raise ValueError("selected_profile must be a non-empty string or null")

    layers = (
        _parse_layers(snapshot["layers"])
        if "layers" in snapshot
        else _default_layers()
    )
    direct: list[str] = []

    final_root = snapshot_root
    if project_root is not None:
        final_root = project_root
        direct.append("project_root")

    if root_markers is not None:
        final_markers = _validate_names(root_markers, "root_marker")
        markers_declared = True
        direct.append("project_root_markers")
    elif parsed_snapshot_markers is not None:
        final_markers = parsed_snapshot_markers
        markers_declared = True
    else:
        final_markers = DEFAULT_ROOT_MARKERS
        markers_declared = False

    if fallback_names is not None:
        final_fallbacks = _validate_names(fallback_names, "fallback_name")
        direct.append("project_doc_fallback_filenames")
    else:
        final_fallbacks = parsed_snapshot_fallbacks

    final_max = snapshot_max
    if max_bytes is not None:
        if isinstance(max_bytes, bool) or max_bytes < 0:
            raise ValueError("--max-bytes must be a non-negative integer")
        final_max = max_bytes
        direct.append("project_doc_max_bytes")

    final_trust = snapshot_trust
    if project_trust is not None:
        if project_trust not in PROJECT_TRUST_VALUES:
            raise ValueError(f"unsupported project_trust: {project_trust}")
        final_trust = project_trust
        direct.append("project_trust")

    final_codex_version = snapshot_codex_version
    if codex_version is not None:
        final_codex_version = codex_version
        direct.append("codex_version")

    final_behavior_profile = snapshot_behavior_profile
    if behavior_profile is not None:
        final_behavior_profile = behavior_profile
        direct.append("behavior_profile")

    final_platform = platform or snapshot_platform
    if platform is not None:
        direct.append("platform")

    if snapshot_path is not None and direct:
        source = "snapshot_plus_flags"
    elif snapshot_path is not None:
        source = "snapshot"
    elif direct:
        source = "direct_flags"
    else:
        source = "defaults"

    return ExplainConfig(
        source=source,
        project_root=final_root,
        project_root_markers=final_markers,
        root_markers_declared=markers_declared,
        fallback_filenames=final_fallbacks,
        project_doc_max_bytes=final_max,
        project_trust=final_trust,
        codex_version=final_codex_version,
        behavior_profile=final_behavior_profile,
        platform=final_platform,
        selected_profile=snapshot_selected_profile,
        layers=layers,
        direct_overrides=tuple(direct),
    )

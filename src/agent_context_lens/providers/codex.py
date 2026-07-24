from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from ..config_snapshot import ExplainConfig
from ..discovery import (
    CandidateFact,
    absolute_lexical,
    find_root_candidates,
    first_symlink_component,
    first_symlink_in_chain,
    inspect_candidate,
    is_directory_without_following,
    is_within,
    path_chain,
    read_regular_candidate,
    relative_display,
)
from ..explain import (
    ContextExplainReport,
    InstructionScope,
    Limitation,
    SourceRecord,
)


EXACT_PROFILES = {
    "codex-cli-0.145.0-darwin-arm64": (
        "0.145.0",
        "darwin-arm64",
    ),
    "codex-cli-0.146.0-alpha.3.1-darwin-arm64": (
        "0.146.0-alpha.3.1",
        "darwin-arm64",
    ),
}
IGNORED_DISCOVERY_DIRECTORIES = {
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


@dataclass(frozen=True)
class _PendingSource:
    record: SourceRecord
    data: bytes | None
    selected: bool = False


class _Limitations:
    def __init__(self) -> None:
        self._items: list[Limitation] = []
        self._keys: set[tuple[str, str | None]] = set()

    def add(
        self,
        code: str,
        message: str,
        source_id: str | None = None,
        *,
        affects_parity: bool = True,
    ) -> None:
        key = (code, source_id)
        if key in self._keys:
            return
        self._keys.add(key)
        self._items.append(
            Limitation(code, message, source_id, affects_parity)
        )

    def freeze(self) -> tuple[Limitation, ...]:
        return tuple(
            sorted(
                self._items,
                key=lambda item: (item.code, item.source_id or ""),
            )
        )


def explain_codex(
    anchor: str | Path,
    *,
    cwd: str | Path | None,
    config: ExplainConfig,
    include_user: bool = False,
    codex_home: str | Path | None = None,
) -> ContextExplainReport:
    anchor_path = absolute_lexical(anchor)
    cwd_path = absolute_lexical(cwd or anchor_path)
    limitations = _Limitations()
    _configuration_limitations(config, limitations)
    exact_profile = _is_exact_profile(config, limitations)

    initial_symlink = first_symlink_component(anchor_path)
    if initial_symlink is None:
        initial_symlink = first_symlink_component(cwd_path)
    if initial_symlink is not None:
        limitations.add(
            "path_symlink_unsupported",
            "A symlinked component occurs in the inspection path.",
        )
        limitations.add(
            "safe_mode_parity_divergence",
            "Safe mode refuses path symlinks and does not claim Codex parity.",
        )
        return _unsupported_report(
            config=config,
            cwd=cwd_path,
            limitations=limitations.freeze(),
            user_requested=include_user,
            project_reason="path_symlink_unsupported",
        )

    if not is_directory_without_following(anchor_path):
        raise ValueError(f"Not a directory: {anchor_path}")
    if not is_directory_without_following(cwd_path):
        raise ValueError(f"Not a directory: {cwd_path}")

    explicit_root = config.project_root is not None
    if explicit_root:
        root = absolute_lexical(config.project_root or ".")
        root_symlink = first_symlink_component(root)
        if root_symlink is not None:
            limitations.add(
                "path_symlink_unsupported",
                "A symlinked component occurs in the declared project root.",
            )
            limitations.add(
                "safe_mode_parity_divergence",
                "Safe mode refuses path symlinks and does not claim parity.",
            )
            return _unsupported_report(
                config=config,
                cwd=cwd_path,
                limitations=limitations.freeze(),
                user_requested=include_user,
                project_reason="path_symlink_unsupported",
            )
        if not is_directory_without_following(root):
            raise ValueError(f"Not a directory: {root}")
        if not is_within(cwd_path, root):
            raise ValueError(
                f"Working directory is outside project root: {cwd_path}"
            )
    else:
        matches = find_root_candidates(
            cwd_path, config.project_root_markers
        )
        if len(matches) > 1:
            limitations.add(
                "project_root_ambiguous",
                "Multiple matching project roots were found; declare one.",
            )
            return _unsupported_report(
                config=config,
                cwd=cwd_path,
                limitations=limitations.freeze(),
                user_requested=include_user,
                project_reason="project_root_ambiguous",
            )
        root = matches[0] if matches else cwd_path
        if not config.root_markers_declared:
            limitations.add(
                "root_markers_assumed_default",
                "Default project root markers were assumed.",
            )

    if not is_within(cwd_path, root):
        raise ValueError(f"Working directory is outside project root: {cwd_path}")

    symlink_path = first_symlink_in_chain(root, cwd_path)
    if symlink_path is not None:
        limitations.add(
            "path_symlink_unsupported",
            "A symlinked directory occurs on the project-root-to-CWD path.",
        )
        limitations.add(
            "safe_mode_parity_divergence",
            "Safe mode refuses path symlinks and does not claim Codex parity.",
        )
        return _unsupported_report(
            config=config,
            cwd=cwd_path,
            limitations=limitations.freeze(),
            user_requested=include_user,
            project_reason="path_symlink_unsupported",
        )

    config_path = root / ".codex" / "config.toml"
    if os.path.lexists(config_path):
        trusted_status = config.layer_status("trusted_project")
        if (
            trusted_status not in {"resolved", "ignored_untrusted"}
            and config.project_trust != "untrusted"
        ):
            limitations.add(
                "toml_config_not_parsed",
                "Project Codex TOML exists but was not parsed.",
            )
        if config.project_trust == "unknown":
            limitations.add(
                "project_trust_unknown",
                "Project trust is unknown for an in-scope Codex config.",
            )
        if trusted_status == "unknown":
            limitations.add(
                "project_config_not_resolved",
                "Trusted project configuration was not resolved.",
            )

    project_pending = _discover_project_sources(
        root,
        cwd_path,
        config=config,
        exact_profile=exact_profile,
        limitations=limitations,
    )
    project_sources = _apply_project_budget(
        project_pending,
        config=config,
        exact_profile=exact_profile,
        limitations=limitations,
    )

    if include_user:
        user_scope, user_sources = _resolve_user_scope(
            config=config,
            codex_home=codex_home,
            exact_profile=exact_profile,
            limitations=limitations,
        )
    else:
        # USER-01: do not construct, stat, enumerate, hash, open, or read
        # CODEX_HOME instruction candidates on this branch.
        user_scope = InstructionScope(
            "user", "not_requested", ("user_scope_not_requested",)
        )
        user_sources = ()

    project_scope_status = (
        "included_with_limitations"
        if any(
            item.state in {"unknown", "unsupported"}
            for item in project_sources
        )
        else "included"
    )
    project_scope_reasons = tuple(
        sorted(
            {
                reason
                for item in project_sources
                for reason in item.reason_codes
                if reason
                in {
                    "configuration_unresolved",
                    "budget_state_unknown",
                    "unsupported_symlink",
                    "broken_symlink",
                }
            }
        )
    )
    project_scope = InstructionScope(
        "project", project_scope_status, project_scope_reasons
    )

    all_sources = _assign_orders((*user_sources, *project_sources))
    frozen_limitations = limitations.freeze()
    if any(source.state == "unsupported" for source in all_sources) and not any(
        source.state.startswith("active") for source in all_sources
    ):
        resolution_status = "unsupported"
    elif frozen_limitations:
        resolution_status = "resolved_with_limitations"
    else:
        resolution_status = "resolved"

    return ContextExplainReport(
        resolution_status=resolution_status,
        agent="codex",
        root=".",
        working_directory=relative_display(cwd_path, root),
        platform=config.platform,
        codex_version=config.codex_version,
        behavior_profile=config.behavior_profile,
        instruction_scopes=(project_scope, user_scope),
        configuration=config,
        sources=all_sources,
        limitations=frozen_limitations,
    )


def _configuration_limitations(
    config: ExplainConfig, limitations: _Limitations
) -> None:
    status_to_limitation = {
        ("cli_override", "unknown"): (
            "codex_cli_overrides_unknown",
            "Future Codex CLI overrides were not declared absent or resolved.",
        ),
        ("selected_profile", "unknown"): (
            "profile_not_resolved",
            "The selected Codex profile was not resolved.",
        ),
        ("user", "not_inspected"): (
            "user_scope_not_inspected",
            "User Codex configuration was not inspected.",
        ),
        ("user", "unknown"): (
            "user_scope_not_inspected",
            "User Codex configuration is unknown.",
        ),
        ("system", "not_inspected"): (
            "system_config_unknown",
            "System configuration was not inspected.",
        ),
        ("system", "unknown"): (
            "system_config_unknown",
            "System configuration was not resolved.",
        ),
    }
    for layer in config.layers:
        mapped = status_to_limitation.get((layer.kind, layer.status))
        if mapped:
            limitations.add(*mapped)
    if (
        config.selected_profile
        and config.layer_status("selected_profile") != "resolved"
    ):
        limitations.add(
            "profile_not_resolved",
            "A selected profile name was supplied without resolved settings.",
        )


def _is_exact_profile(
    config: ExplainConfig, limitations: _Limitations
) -> bool:
    if config.behavior_profile == "official-contract":
        return False
    expected = EXACT_PROFILES.get(config.behavior_profile)
    if expected is None:
        limitations.add(
            "behavior_profile_unverified",
            "The selected behavior profile has no accepted evidence.",
        )
        return False
    expected_version, expected_platform = expected
    valid = True
    if config.codex_version != expected_version:
        limitations.add(
            "codex_version_outside_profile",
            "The declared Codex version does not match the selected profile.",
        )
        valid = False
    if config.platform != expected_platform:
        limitations.add(
            "platform_not_validated",
            "The declared platform does not match the selected profile.",
        )
        valid = False
    return valid


def _discover_project_sources(
    root: Path,
    cwd: Path,
    *,
    config: ExplainConfig,
    exact_profile: bool,
    limitations: _Limitations,
) -> tuple[_PendingSource, ...]:
    result: list[_PendingSource] = []
    active_chain = path_chain(root, cwd)
    for directory_path in active_chain:
        directory_display = relative_display(directory_path, root)
        candidates = _candidate_facts(
            directory_path,
            root=root,
            directory_display=directory_display,
            fallback_names=config.fallback_filenames,
        )
        result.extend(
            _select_project_directory(
                candidates,
                root=root,
                exact_profile=exact_profile,
                limitations=limitations,
            )
        )
    active_directories = set(active_chain)
    recognized = {
        "AGENTS.override.md": "override",
        "AGENTS.md": "base",
        **{name: "fallback" for name in config.fallback_filenames},
    }
    for current_root, directories, filenames in os.walk(
        root, followlinks=False
    ):
        current = Path(current_root)
        directories[:] = sorted(
            name
            for name in directories
            if name not in IGNORED_DISCOVERY_DIRECTORIES
            and not (current / name).is_symlink()
        )
        if current in active_directories:
            continue
        for filename in sorted(filenames):
            kind = recognized.get(filename)
            if kind is None:
                continue
            path = current / filename
            fact = inspect_candidate(
                path,
                display_path=path.relative_to(root).as_posix(),
                directory=relative_display(current, root),
                candidate_kind=kind,
            )
            if fact is None:
                continue
            pending = _pending_from_fact(fact, "project", root)
            result.append(
                replace(
                    pending,
                    record=replace(
                        pending.record,
                        state="inactive",
                        reason_codes=("outside_working_directory_chain",),
                        evidence_class="official_contract",
                    ),
                )
            )
    return tuple(result)


def _candidate_facts(
    directory: Path,
    *,
    root: Path,
    directory_display: str,
    fallback_names: Iterable[str],
) -> tuple[CandidateFact, ...]:
    definitions = [
        ("AGENTS.override.md", "override"),
        ("AGENTS.md", "base"),
        *((name, "fallback") for name in fallback_names),
    ]
    result: list[CandidateFact] = []
    for filename, kind in definitions:
        path = directory / filename
        display = path.relative_to(root).as_posix()
        fact = inspect_candidate(
            path,
            display_path=display,
            directory=directory_display,
            candidate_kind=kind,
        )
        if fact is not None:
            result.append(fact)
    return tuple(result)


def _select_project_directory(
    facts: tuple[CandidateFact, ...],
    *,
    root: Path,
    exact_profile: bool,
    limitations: _Limitations,
) -> tuple[_PendingSource, ...]:
    if not facts:
        return ()
    pending = [_pending_from_fact(fact, "project", root) for fact in facts]
    highest = pending[0]
    if highest.record.state == "unsupported":
        _add_symlink_limitations(highest.record, limitations)
        return tuple(
            [
                highest,
                *[
                    replace(
                        item,
                        record=replace(
                            item.record,
                            state="unknown",
                            reason_codes=(
                                "lower_priority_candidate",
                                "configuration_unresolved",
                            ),
                            evidence_class="unknown",
                        ),
                    )
                    for item in pending[1:]
                ],
            ]
        )

    data = highest.data or b""
    empty_reason = _empty_reason(data)
    if empty_reason is not None:
        if exact_profile:
            result = [
                replace(
                    highest,
                    record=replace(
                        highest.record,
                        state="inactive",
                        reason_codes=(empty_reason,),
                        evidence_class="versioned_observation",
                    ),
                )
            ]
            result.extend(
                replace(
                    item,
                    record=replace(
                        item.record,
                        state="inactive",
                        reason_codes=("lower_priority_candidate",),
                        evidence_class="versioned_observation",
                    ),
                )
                for item in pending[1:]
            )
            return tuple(result)

        limitations.add(
            (
                "whitespace_empty_semantics_unverified"
                if empty_reason == "empty_whitespace_only"
                else "project_empty_candidate_semantics_unverified"
            ),
            "Project empty-candidate retry behavior is not established.",
            highest.record.source_id,
        )
        return tuple(
            replace(
                item,
                record=replace(
                    item.record,
                    state="unknown",
                    reason_codes=(
                        (
                            empty_reason
                            if index == 0
                            else "lower_priority_candidate"
                        ),
                        "empty_candidate_retry_unknown",
                    ),
                    evidence_class="unknown",
                ),
            )
            for index, item in enumerate(pending)
        )

    selected_reason = "selected_highest_priority"
    result = [
        replace(
            highest,
            selected=True,
            record=replace(
                highest.record,
                state="active_full",
                reason_codes=(selected_reason,),
                evidence_class="official_contract",
            ),
        )
    ]
    shadow_reason = {
        "override": "shadowed_by_override",
        "base": "shadowed_by_base",
        "fallback": "shadowed_by_fallback",
    }[highest.record.candidate_kind]
    for item in pending[1:]:
        result.append(
            replace(
                item,
                record=replace(
                    item.record,
                    state="inactive",
                    reason_codes=(shadow_reason,),
                    evidence_class="official_contract",
                ),
            )
        )
    return tuple(result)


def _pending_from_fact(
    fact: CandidateFact, scope: str, root: Path | None
) -> _PendingSource:
    source_id = (
        f"{scope}:{fact.directory}:{fact.candidate_kind}:{fact.path.name}"
    )
    if fact.is_symlink:
        try:
            target_text = os.readlink(fact.path)
            target = Path(target_text)
            if not target.is_absolute():
                target = fact.path.parent / target
            broken = not os.path.lexists(target)
        except OSError:
            broken = True
        record = SourceRecord(
            source_id=source_id,
            display_path=fact.display_path,
            scope=scope,
            directory=fact.directory if scope == "project" else None,
            candidate_kind=fact.candidate_kind,
            order=None,
            state="unsupported",
            reason_codes=(
                "broken_symlink" if broken else "unsupported_symlink",
            ),
            evidence_class="unknown",
            source_bytes=None,
            loaded_bytes=None,
            rendered_utf8_bytes=None,
            separator_bytes_before=None,
            partial=None,
            sha256_source=None,
            sha256_loaded=None,
            encoding_status="not_read",
        )
        return _PendingSource(record, None)
    if not fact.is_regular_file:
        record = SourceRecord(
            source_id=source_id,
            display_path=fact.display_path,
            scope=scope,
            directory=fact.directory if scope == "project" else None,
            candidate_kind=fact.candidate_kind,
            order=None,
            state="unsupported",
            reason_codes=("unsupported_file_type",),
            evidence_class="unknown",
            source_bytes=None,
            loaded_bytes=None,
            rendered_utf8_bytes=None,
            separator_bytes_before=None,
            partial=None,
            sha256_source=None,
            sha256_loaded=None,
            encoding_status="not_read",
        )
        return _PendingSource(record, None)

    data = read_regular_candidate(fact)
    record = SourceRecord(
        source_id=source_id,
        display_path=fact.display_path,
        scope=scope,
        directory=fact.directory if scope == "project" else None,
        candidate_kind=fact.candidate_kind,
        order=None,
        state="inactive",
        reason_codes=(),
        evidence_class="official_contract",
        source_bytes=len(data),
        loaded_bytes=None,
        rendered_utf8_bytes=None,
        separator_bytes_before=None,
        partial=None,
        sha256_source=_sha256(data),
        sha256_loaded=None,
        encoding_status=_source_encoding(data),
    )
    return _PendingSource(record, data)


def _apply_project_budget(
    pending: tuple[_PendingSource, ...],
    *,
    config: ExplainConfig,
    exact_profile: bool,
    limitations: _Limitations,
) -> tuple[SourceRecord, ...]:
    selected_indexes = [
        index for index, item in enumerate(pending) if item.selected
    ]
    if not selected_indexes:
        return tuple(item.record for item in pending)

    records = [item.record for item in pending]
    raw_remaining = config.project_doc_max_bytes
    separator_remaining = config.project_doc_max_bytes
    loaded_count = 0
    disputed = False
    for index in selected_indexes:
        item = pending[index]
        data = item.data or b""
        separator = 0 if loaded_count == 0 else 2
        if exact_profile:
            if raw_remaining <= 0:
                records[index] = replace(
                    item.record,
                    state="inactive",
                    reason_codes=("budget_exhausted",),
                    evidence_class="versioned_observation",
                    loaded_bytes=None,
                    rendered_utf8_bytes=None,
                    separator_bytes_before=None,
                    partial=None,
                    sha256_loaded=None,
                )
                continue
            loaded = data[:raw_remaining]
            raw_remaining -= len(loaded)
            partial = len(loaded) < len(data)
            encoding = _loaded_encoding(loaded, partial=partial)
            rendered_bytes = len(
                loaded.decode("utf-8", errors="replace").encode("utf-8")
            )
            records[index] = replace(
                item.record,
                state="active_partial" if partial else "active_full",
                reason_codes=(
                    ("budget_partial_prefix",)
                    if partial
                    else ("selected_version_profile",)
                ),
                evidence_class="versioned_observation",
                loaded_bytes=len(loaded),
                rendered_utf8_bytes=rendered_bytes,
                separator_bytes_before=separator,
                partial=partial,
                sha256_loaded=_sha256(loaded) if loaded else None,
                encoding_status=encoding,
            )
            loaded_count += 1
            continue

        if disputed:
            records[index] = replace(
                item.record,
                state="unknown",
                reason_codes=("budget_state_unknown",),
                evidence_class="unknown",
                loaded_bytes=None,
                rendered_utf8_bytes=None,
                separator_bytes_before=None,
                partial=None,
                sha256_loaded=None,
            )
            continue

        fits_raw = len(data) <= raw_remaining
        fits_with_separator = len(data) + separator <= separator_remaining
        valid_source = _source_encoding(data) == "valid_utf8"
        if fits_raw and fits_with_separator and valid_source:
            records[index] = replace(
                item.record,
                state="active_full",
                reason_codes=("selected_highest_priority",),
                evidence_class="official_contract",
                loaded_bytes=len(data),
                rendered_utf8_bytes=len(data),
                separator_bytes_before=separator,
                partial=False,
                sha256_loaded=_sha256(data) if data else None,
                encoding_status="valid_utf8",
            )
            raw_remaining -= len(data)
            separator_remaining -= len(data) + separator
            loaded_count += 1
            continue

        disputed = True
        records[index] = replace(
            item.record,
            state="unknown",
            reason_codes=("budget_state_unknown",),
            evidence_class="unknown",
            loaded_bytes=None,
            rendered_utf8_bytes=None,
            separator_bytes_before=None,
            partial=None,
            sha256_loaded=None,
        )
        limitations.add(
            "byte_budget_semantics_unverified",
            "Byte-budget behavior is not established by the selected profile.",
            item.record.source_id,
        )
        if separator:
            limitations.add(
                "separator_accounting_unverified",
                "Inter-source separator accounting is not established.",
                item.record.source_id,
            )
        if not valid_source:
            limitations.add(
                "invalid_utf8_semantics_unverified",
                "Invalid UTF-8 behavior is not established.",
                item.record.source_id,
            )

    return tuple(records)


def _resolve_user_scope(
    *,
    config: ExplainConfig,
    codex_home: str | Path | None,
    exact_profile: bool,
    limitations: _Limitations,
) -> tuple[InstructionScope, tuple[SourceRecord, ...]]:
    home = absolute_lexical(
        codex_home
        or os.environ.get("CODEX_HOME")
        or (Path.home() / ".codex")
    )
    if first_symlink_component(home) is not None:
        limitations.add(
            "path_symlink_unsupported",
            "A symlinked CODEX_HOME is refused in safe mode.",
        )
        limitations.add(
            "safe_mode_parity_divergence",
            "Safe mode refuses CODEX_HOME symlinks.",
        )
        return (
            InstructionScope(
                "user", "unsupported", ("path_symlink_unsupported",)
            ),
            (),
        )
    if not home.exists():
        return InstructionScope("user", "included", ()), ()
    if not home.is_dir():
        limitations.add(
            "path_symlink_unsupported",
            "CODEX_HOME is not a safe directory.",
        )
        return (
            InstructionScope(
                "user", "unsupported", ("path_symlink_unsupported",)
            ),
            (),
        )

    facts: list[CandidateFact] = []
    for filename, kind in (
        ("AGENTS.override.md", "override"),
        ("AGENTS.md", "base"),
    ):
        fact = inspect_candidate(
            home / filename,
            display_path=f"$CODEX_HOME/{filename}",
            directory="",
            candidate_kind=kind,
        )
        if fact is not None:
            facts.append(fact)
    pending = [
        _pending_from_fact(fact, "user", root=None) for fact in facts
    ]
    if not pending:
        return InstructionScope("user", "included", ()), ()

    for index, item in enumerate(pending):
        if item.record.state == "unsupported":
            _add_symlink_limitations(item.record, limitations)
            return (
                InstructionScope(
                    "user",
                    "unsupported",
                    item.record.reason_codes,
                ),
                tuple(entry.record for entry in pending),
            )
        data = item.data or b""
        empty_reason = _empty_reason(data)
        if empty_reason is not None:
            if exact_profile:
                pending[index] = replace(
                    item,
                    record=replace(
                        item.record,
                        state="inactive",
                        reason_codes=(empty_reason,),
                        evidence_class="versioned_observation",
                    ),
                )
                continue
            limitations.add(
                (
                    "whitespace_empty_semantics_unverified"
                    if empty_reason == "empty_whitespace_only"
                    else "global_empty_candidate_semantics_unverified"
                ),
                "User-global empty-candidate retry behavior is not established.",
                item.record.source_id,
            )
            unknown = tuple(
                replace(
                    entry.record,
                    state="unknown",
                    reason_codes=(
                        (
                            empty_reason
                            if entry_index == index
                            else "lower_priority_candidate"
                        ),
                        "empty_candidate_retry_unknown",
                    ),
                    evidence_class="unknown",
                )
                for entry_index, entry in enumerate(pending)
            )
            return (
                InstructionScope(
                    "user",
                    "included_with_limitations",
                    ("empty_candidate_retry_unknown",),
                ),
                unknown,
            )

        selected = replace(
            item.record,
            state="active_full",
            reason_codes=(
                "selected_version_profile"
                if exact_profile
                else "selected_highest_priority",
            ),
            evidence_class=(
                "versioned_observation"
                if exact_profile
                else "official_contract"
            ),
            loaded_bytes=len(data),
            rendered_utf8_bytes=len(
                data.decode("utf-8", errors="replace").encode("utf-8")
            ),
            separator_bytes_before=0,
            partial=False,
            sha256_loaded=_sha256(data) if data else None,
            encoding_status=_loaded_encoding(data, partial=False),
        )
        pending[index] = replace(item, record=selected, selected=True)
        shadow_reason = (
            "shadowed_by_override"
            if item.record.candidate_kind == "override"
            else "shadowed_by_base"
        )
        for lower_index in range(index + 1, len(pending)):
            lower = pending[lower_index]
            pending[lower_index] = replace(
                lower,
                record=replace(
                    lower.record,
                    state="inactive",
                    reason_codes=(shadow_reason,),
                    evidence_class=selected.evidence_class,
                ),
            )
        return (
            InstructionScope("user", "included", ()),
            tuple(entry.record for entry in pending),
        )

    return (
        InstructionScope("user", "included", ()),
        tuple(entry.record for entry in pending),
    )


def _assign_orders(
    sources: tuple[SourceRecord, ...],
) -> tuple[SourceRecord, ...]:
    order = 1
    result: list[SourceRecord] = []
    for source in sources:
        if source.state in {"active_full", "active_partial"}:
            result.append(replace(source, order=order))
            order += 1
        else:
            result.append(source)
    return tuple(result)


def _unsupported_report(
    *,
    config: ExplainConfig,
    cwd: Path,
    limitations: tuple[Limitation, ...],
    user_requested: bool,
    project_reason: str,
) -> ContextExplainReport:
    user_scope = (
        InstructionScope("user", "included_with_limitations", ())
        if user_requested
        else InstructionScope(
            "user", "not_requested", ("user_scope_not_requested",)
        )
    )
    return ContextExplainReport(
        resolution_status="unsupported",
        agent="codex",
        root=".",
        working_directory=".",
        platform=config.platform,
        codex_version=config.codex_version,
        behavior_profile=config.behavior_profile,
        instruction_scopes=(
            InstructionScope(
                "project", "unsupported", (project_reason,)
            ),
            user_scope,
        ),
        configuration=config,
        sources=(),
        limitations=limitations,
    )


def _add_symlink_limitations(
    record: SourceRecord, limitations: _Limitations
) -> None:
    code = record.reason_codes[0]
    limitations.add(
        code,
        "An instruction-file symlink is refused in safe mode.",
        record.source_id,
    )
    limitations.add(
        "safe_mode_parity_divergence",
        "Safe mode refuses instruction symlinks and does not claim parity.",
        record.source_id,
    )


def _empty_reason(data: bytes) -> str | None:
    if not data:
        return "empty_zero_bytes"
    if all(byte in b" \t\r\n\v\f" for byte in data):
        return "empty_whitespace_only"
    return None


def _source_encoding(data: bytes) -> str:
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return "invalid_utf8"
    return "valid_utf8"


def _loaded_encoding(data: bytes, *, partial: bool) -> str:
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        if partial and error.reason == "unexpected end of data":
            return "split_multibyte_boundary"
        return "invalid_utf8"
    return "valid_utf8"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

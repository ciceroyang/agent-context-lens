from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from agent_context_lens import discovery as discovery_module
from agent_context_lens.config_snapshot import (
    ConfigLayer,
    ExplainConfig,
    build_explain_config,
)
from agent_context_lens.providers.codex import explain_codex


PROFILE = "codex-cli-0.145.0-darwin-arm64"


def resolved_config(
    root: Path | None,
    *,
    max_bytes: int = 32768,
    fallback_names: tuple[str, ...] = (),
    profile: str = "official-contract",
    version: str = "unknown",
    platform: str = "darwin-arm64",
    root_markers: tuple[str, ...] = (".git",),
    root_markers_declared: bool = True,
) -> ExplainConfig:
    statuses = {
        "cli_override": "not_present",
        "trusted_project": "not_present",
        "selected_profile": "not_present",
        "user": "not_present",
        "system": "not_present",
        "defaults": "resolved",
    }
    return ExplainConfig(
        source="test",
        project_root=str(root) if root is not None else None,
        project_root_markers=root_markers,
        root_markers_declared=root_markers_declared,
        fallback_filenames=fallback_names,
        project_doc_max_bytes=max_bytes,
        project_trust="trusted",
        codex_version=version,
        behavior_profile=profile,
        platform=platform,
        selected_profile=None,
        layers=tuple(
            ConfigLayer(kind, statuses[kind])
            for kind in (
                "cli_override",
                "trusted_project",
                "selected_profile",
                "user",
                "system",
                "defaults",
            )
        ),
        direct_overrides=(),
    )


def exact_config(
    root: Path, *, max_bytes: int = 32768
) -> ExplainConfig:
    return resolved_config(
        root,
        max_bytes=max_bytes,
        profile=PROFILE,
        version="0.145.0",
    )


def source_map(report):
    return {source.display_path: source for source in report.sources}


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def install_swap_before_open(
    monkeypatch, candidate: Path, external_target: Path
):
    original_open = discovery_module.os.open
    original_read = discovery_module.os.read
    target_metadata = external_target.stat()
    swapped = []
    external_reads = []
    observed_flags = []

    def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
        if Path(path) == candidate and not swapped:
            candidate.unlink()
            candidate.symlink_to(external_target)
            swapped.append(True)
            observed_flags.append(flags)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    def observed_read(descriptor, size):
        metadata = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) == (
            target_metadata.st_dev,
            target_metadata.st_ino,
        ):
            external_reads.append(size)
        return original_read(descriptor, size)

    monkeypatch.setattr(discovery_module.os, "open", swapping_open)
    monkeypatch.setattr(discovery_module.os, "read", observed_read)
    return swapped, external_reads, observed_flags


def test_root_01_explicit_root_single_agents(tmp_path):
    write(tmp_path / "AGENTS.md", b"root")

    report = explain_codex(
        tmp_path,
        cwd=tmp_path,
        config=resolved_config(tmp_path),
    )

    source = source_map(report)["AGENTS.md"]
    assert report.resolution_status == "resolved"
    assert source.state == "active_full"
    assert source.loaded_bytes == 4
    assert source.rendered_utf8_bytes == 4
    assert source.order == 1


def test_root_02_nested_chain_and_root_03_below_cwd(tmp_path):
    nested = tmp_path / "services"
    below = nested / "payments"
    write(tmp_path / "AGENTS.md", b"root")
    write(nested / "AGENTS.md", b"services")
    write(below / "AGENTS.md", b"payments")

    report = explain_codex(
        tmp_path,
        cwd=nested,
        config=resolved_config(tmp_path),
    )

    sources = source_map(report)
    assert sources["AGENTS.md"].order == 1
    assert sources["services/AGENTS.md"].order == 2
    assert sources["services/payments/AGENTS.md"].state == "inactive"
    assert sources[
        "services/payments/AGENTS.md"
    ].reason_codes == ("outside_working_directory_chain",)


def test_root_04_without_marker_checks_only_cwd(tmp_path):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"parent")
    write(nested / "AGENTS.md", b"cwd")

    report = explain_codex(
        tmp_path,
        cwd=nested,
        config=resolved_config(None),
    )

    assert report.working_directory == "."
    assert [item.display_path for item in report.sources] == ["AGENTS.md"]


def test_root_05_custom_marker(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / ".acl-root").write_text("", encoding="utf-8")
    write(tmp_path / "AGENTS.md", b"root")

    config = resolved_config(
        None,
        root_markers=(".acl-root",),
        root_markers_declared=True,
    )
    report = explain_codex(tmp_path, cwd=nested, config=config)

    assert report.working_directory == "nested"
    assert source_map(report)["AGENTS.md"].state == "active_full"


def test_root_06_default_marker_limitation(tmp_path):
    (tmp_path / ".git").mkdir()
    config = resolved_config(
        None,
        root_markers=(".git",),
        root_markers_declared=False,
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert "root_markers_assumed_default" in {
        item.code for item in report.limitations
    }


def test_root_07_rejects_cwd_outside_root(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    with pytest.raises(ValueError, match="outside project root"):
        explain_codex(root, cwd=outside, config=resolved_config(root))


def test_root_08_multiple_roots_are_unsupported(tmp_path):
    nested = tmp_path / "nested"
    (tmp_path / ".git").mkdir()
    (nested / ".git").mkdir(parents=True)

    report = explain_codex(
        tmp_path,
        cwd=nested,
        config=resolved_config(None),
    )

    assert report.resolution_status == "unsupported"
    assert "project_root_ambiguous" in {
        item.code for item in report.limitations
    }


def test_cand_p_01_base_and_cand_p_02_override(tmp_path):
    write(tmp_path / "AGENTS.md", b"base")
    report = explain_codex(
        tmp_path, cwd=tmp_path, config=resolved_config(tmp_path)
    )
    assert source_map(report)["AGENTS.md"].state == "active_full"

    write(tmp_path / "AGENTS.override.md", b"override")
    report = explain_codex(
        tmp_path, cwd=tmp_path, config=resolved_config(tmp_path)
    )
    sources = source_map(report)
    assert sources["AGENTS.override.md"].state == "active_full"
    assert sources["AGENTS.md"].reason_codes == ("shadowed_by_override",)


def test_cand_p_03_fallback_order(tmp_path):
    write(tmp_path / "FALLBACK1.md", b"first")
    write(tmp_path / "FALLBACK2.md", b"second")

    report = explain_codex(
        tmp_path,
        cwd=tmp_path,
        config=resolved_config(
            tmp_path, fallback_names=("FALLBACK1.md", "FALLBACK2.md")
        ),
    )

    sources = source_map(report)
    assert sources["FALLBACK1.md"].state == "active_full"
    assert sources["FALLBACK2.md"].reason_codes == ("shadowed_by_fallback",)


def test_cand_g_01_base_and_cand_g_02_override(tmp_path):
    root = tmp_path / "repo"
    home = tmp_path / "home"
    root.mkdir()
    home.mkdir()
    write(home / "AGENTS.md", b"base")

    report = explain_codex(
        root,
        cwd=root,
        config=resolved_config(root),
        include_user=True,
        codex_home=home,
    )
    assert source_map(report)["$CODEX_HOME/AGENTS.md"].state == "active_full"

    write(home / "AGENTS.override.md", b"override")
    report = explain_codex(
        root,
        cwd=root,
        config=resolved_config(root),
        include_user=True,
        codex_home=home,
    )
    sources = source_map(report)
    assert sources["$CODEX_HOME/AGENTS.override.md"].state == "active_full"
    assert sources[
        "$CODEX_HOME/AGENTS.md"
    ].reason_codes == ("shadowed_by_override",)


@pytest.mark.parametrize("empty", [b"", b" \t\n"])
def test_empty_p_alpha_profile_blocks_lower_candidate(tmp_path, empty):
    write(tmp_path / "AGENTS.override.md", empty)
    write(tmp_path / "AGENTS.md", b"base")

    report = explain_codex(
        tmp_path, cwd=tmp_path, config=exact_config(tmp_path)
    )

    sources = source_map(report)
    assert not any(
        item.state.startswith("active") for item in report.sources
    )
    assert sources["AGENTS.override.md"].evidence_class == (
        "versioned_observation"
    )
    assert sources["AGENTS.md"].reason_codes == ("lower_priority_candidate",)


def test_empty_p_official_profile_remains_unknown(tmp_path):
    write(tmp_path / "AGENTS.override.md", b"")
    write(tmp_path / "AGENTS.md", b"base")

    report = explain_codex(
        tmp_path, cwd=tmp_path, config=resolved_config(tmp_path)
    )

    assert source_map(report)["AGENTS.override.md"].state == "unknown"
    assert "project_empty_candidate_semantics_unverified" in {
        item.code for item in report.limitations
    }


def test_empty_p_whitespace_official_profile_remains_unknown(tmp_path):
    write(tmp_path / "AGENTS.override.md", b" \t\n")
    write(tmp_path / "AGENTS.md", b"base")

    report = explain_codex(
        tmp_path, cwd=tmp_path, config=resolved_config(tmp_path)
    )

    assert source_map(report)["AGENTS.override.md"].state == "unknown"
    assert "whitespace_empty_semantics_unverified" in {
        item.code for item in report.limitations
    }


def test_empty_g_exact_profile_retries_base(tmp_path):
    root = tmp_path / "repo"
    home = tmp_path / "home"
    root.mkdir()
    home.mkdir()
    write(home / "AGENTS.override.md", b"")
    write(home / "AGENTS.md", b"base")

    report = explain_codex(
        root,
        cwd=root,
        config=exact_config(root),
        include_user=True,
        codex_home=home,
    )

    sources = source_map(report)
    assert sources[
        "$CODEX_HOME/AGENTS.override.md"
    ].reason_codes == ("empty_zero_bytes",)
    assert sources["$CODEX_HOME/AGENTS.md"].state == "active_full"


def test_empty_g_whitespace_official_profile_remains_unknown(tmp_path):
    root = tmp_path / "repo"
    home = tmp_path / "home"
    root.mkdir()
    home.mkdir()
    write(home / "AGENTS.override.md", b" \n")
    write(home / "AGENTS.md", b"base")

    report = explain_codex(
        root,
        cwd=root,
        config=resolved_config(root),
        include_user=True,
        codex_home=home,
    )

    assert source_map(report)["$CODEX_HOME/AGENTS.override.md"].state == (
        "unknown"
    )
    assert "whitespace_empty_semantics_unverified" in {
        item.code for item in report.limitations
    }


def test_byte_03_separator_does_not_consume_named_profile_cap(tmp_path):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"ROOT1234")
    write(nested / "AGENTS.md", b"NEST5678")

    report = explain_codex(
        tmp_path,
        cwd=nested,
        config=exact_config(tmp_path, max_bytes=9),
    )

    root_source = source_map(report)["AGENTS.md"]
    nested_source = source_map(report)["nested/AGENTS.md"]
    assert root_source.loaded_bytes == 8
    assert nested_source.state == "active_partial"
    assert nested_source.loaded_bytes == 1
    assert nested_source.rendered_utf8_bytes == 1
    assert nested_source.separator_bytes_before == 2


def test_byte_06_split_multibyte_tracks_raw_and_rendered_bytes(tmp_path):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"ROOT")
    write(nested / "AGENTS.md", "汉字🙂Z".encode())

    report = explain_codex(
        tmp_path,
        cwd=nested,
        config=exact_config(tmp_path, max_bytes=11),
    )

    source = source_map(report)["nested/AGENTS.md"]
    raw_prefix = "汉字".encode() + b"\xf0"
    assert source.state == "active_partial"
    assert source.loaded_bytes == 7
    assert source.rendered_utf8_bytes == 9
    assert source.encoding_status == "split_multibyte_boundary"
    assert source.sha256_loaded == hashlib.sha256(raw_prefix).hexdigest()


def test_byte_07_invalid_utf8_tracks_replacement_expansion(tmp_path):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"ROOT")
    write(nested / "AGENTS.md", b"OK\xffBAD")

    report = explain_codex(
        tmp_path, cwd=nested, config=exact_config(tmp_path)
    )

    source = source_map(report)["nested/AGENTS.md"]
    assert source.loaded_bytes == 6
    assert source.rendered_utf8_bytes == 8
    assert source.encoding_status == "invalid_utf8"


def test_byte_official_disputed_separator_remains_unknown(tmp_path):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"ROOT1234")
    write(nested / "AGENTS.md", b"NEST5678")

    report = explain_codex(
        tmp_path,
        cwd=nested,
        config=resolved_config(tmp_path, max_bytes=9),
    )

    source = source_map(report)["nested/AGENTS.md"]
    assert source.state == "unknown"
    assert source.loaded_bytes is None
    assert "byte_budget_semantics_unverified" in {
        item.code for item in report.limitations
    }
    assert "separator_accounting_unverified" in {
        item.code for item in report.limitations
    }


@pytest.mark.parametrize(
    ("case_id", "root_bytes", "nested_bytes", "cap", "expected"),
    [
        ("BYTE-00", b"ROOT1234", b"NEST5678", 0, (None, None, None)),
        ("BYTE-01", b"ROOT1234", b"NEST5678", 7, (7, None, None)),
        ("BYTE-02", b"ROOT1234", b"NEST5678", 8, (8, None, None)),
        ("BYTE-04", b"ROOT1234", b"NEST5678", 13, (8, 5, 5)),
        ("BYTE-05", b"ROOT", "汉字🙂Z".encode(), 10, (4, 6, 6)),
        ("BYTE-08", b"ROOT\n", b"NEST\n", 8, (5, 3, 3)),
        ("BYTE-09", b"ROOT", b"NEST", 32768, (4, 4, 4)),
    ],
)
def test_remaining_named_byte_matrix(
    tmp_path, case_id, root_bytes, nested_bytes, cap, expected
):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", root_bytes)
    write(nested / "AGENTS.md", nested_bytes)

    report = explain_codex(
        tmp_path,
        cwd=nested,
        config=exact_config(tmp_path, max_bytes=cap),
    )
    sources = source_map(report)
    root_source = sources["AGENTS.md"]
    nested_source = sources["nested/AGENTS.md"]
    root_loaded, nested_loaded, nested_rendered = expected
    assert root_source.loaded_bytes == root_loaded, case_id
    assert nested_source.loaded_bytes == nested_loaded, case_id
    assert nested_source.rendered_utf8_bytes == nested_rendered, case_id


def test_byte_08_trailing_newline_keeps_two_byte_separator(tmp_path):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"R\n")
    write(nested / "AGENTS.md", b"N\n")

    report = explain_codex(
        tmp_path, cwd=nested, config=exact_config(tmp_path)
    )
    nested_source = source_map(report)["nested/AGENTS.md"]

    assert nested_source.separator_bytes_before == 2
    assert nested_source.loaded_bytes == 2


def test_user_01_default_does_not_touch_codex_home_candidates(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    home = tmp_path / "codex-home"
    root.mkdir()
    home.mkdir()
    write(root / "AGENTS.md", b"project")
    write(home / "AGENTS.override.md", b"global")
    write(home / "AGENTS.md", b"base")
    candidates = {
        home / "AGENTS.override.md",
        home / "AGENTS.md",
    }
    events = []
    original_lstat = Path.lstat
    original_stat = Path.stat
    original_open = Path.open
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes
    original_os_stat = os.stat
    original_os_lstat = os.lstat
    original_scandir = os.scandir

    def is_candidate(value):
        if isinstance(value, int):
            return False
        try:
            normalized = Path(os.path.abspath(os.fspath(value)))
        except (TypeError, ValueError):
            return False
        return normalized in candidates

    def observed_lstat(self):
        if is_candidate(self):
            events.append(("lstat", self.name))
        return original_lstat(self)

    def observed_stat(self, *args, **kwargs):
        if is_candidate(self):
            events.append(("stat", self.name))
        return original_stat(self, *args, **kwargs)

    def observed_open(self, *args, **kwargs):
        if is_candidate(self):
            events.append(("open", self.name))
        return original_open(self, *args, **kwargs)

    def observed_read_text(self, *args, **kwargs):
        if is_candidate(self):
            events.append(("read_text", self.name))
        return original_read_text(self, *args, **kwargs)

    def observed_read_bytes(self):
        if is_candidate(self):
            events.append(("read_bytes", self.name))
        return original_read_bytes(self)

    def observed_os_stat(path, *args, **kwargs):
        if is_candidate(path):
            events.append(("os.stat", Path(path).name))
        return original_os_stat(path, *args, **kwargs)

    def observed_os_lstat(path, *args, **kwargs):
        if is_candidate(path):
            events.append(("os.lstat", Path(path).name))
        return original_os_lstat(path, *args, **kwargs)

    def observed_scandir(path="."):
        if is_candidate(path):
            events.append(("os.scandir", Path(path).name))
        return original_scandir(path)

    monkeypatch.setattr(Path, "lstat", observed_lstat)
    monkeypatch.setattr(Path, "stat", observed_stat)
    monkeypatch.setattr(Path, "open", observed_open)
    monkeypatch.setattr(Path, "read_text", observed_read_text)
    monkeypatch.setattr(Path, "read_bytes", observed_read_bytes)
    monkeypatch.setattr(os, "stat", observed_os_stat)
    monkeypatch.setattr(os, "lstat", observed_os_lstat)
    monkeypatch.setattr(os, "scandir", observed_scandir)

    report = explain_codex(
        root,
        cwd=root,
        config=resolved_config(root),
        include_user=False,
        codex_home=home,
    )

    assert events == []
    user_scope = next(
        item for item in report.instruction_scopes if item.scope == "user"
    )
    assert user_scope.status == "not_requested"
    assert user_scope.reason_codes == ("user_scope_not_requested",)
    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert "user_scope_not_requested" in rendered
        assert "GLOBAL" not in rendered


def test_user_02_opt_in_redacts_and_hashes_selected_source(tmp_path):
    root = tmp_path / "repo"
    home = tmp_path / "private-home"
    root.mkdir()
    home.mkdir()
    write(root / "AGENTS.md", b"project")
    global_bytes = b"global override"
    write(home / "AGENTS.override.md", global_bytes)
    write(home / "AGENTS.md", b"shadowed")

    report = explain_codex(
        root,
        cwd=root,
        config=resolved_config(root),
        include_user=True,
        codex_home=home,
    )

    sources = source_map(report)
    selected = sources["$CODEX_HOME/AGENTS.override.md"]
    assert selected.state == "active_full"
    assert selected.source_bytes == len(global_bytes)
    assert selected.sha256_source == hashlib.sha256(global_bytes).hexdigest()
    assert sources[
        "$CODEX_HOME/AGENTS.md"
    ].reason_codes == ("shadowed_by_override",)
    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert "$CODEX_HOME/AGENTS.override.md" in rendered
        assert str(home) not in rendered
        assert selected.sha256_source in rendered


def test_sym_01_instruction_symlink_is_refused_without_target_read(
    tmp_path, monkeypatch
):
    target = tmp_path / "target.md"
    target.write_bytes(b"secret target")
    (tmp_path / "AGENTS.md").symlink_to(target)
    reads = []
    original_read_bytes = Path.read_bytes

    def observed_read_bytes(self):
        if self == target:
            reads.append(self)
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", observed_read_bytes)
    report = explain_codex(
        tmp_path, cwd=tmp_path, config=resolved_config(tmp_path)
    )

    source = source_map(report)["AGENTS.md"]
    assert source.state == "unsupported"
    assert source.source_bytes is None
    assert reads == []
    assert "safe_mode_parity_divergence" in {
        item.code for item in report.limitations
    }


def test_sym_02_external_instruction_symlink_redacts_target(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    root.mkdir()
    target = tmp_path / "outside-secret.md"
    target.write_bytes(b"must not read")
    (root / "AGENTS.md").symlink_to(target)
    reads = []
    original_read_bytes = Path.read_bytes

    def observed_read_bytes(self):
        if self == target:
            reads.append(self)
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", observed_read_bytes)
    report = explain_codex(
        root, cwd=root, config=resolved_config(root)
    )

    assert reads == []
    source = source_map(report)["AGENTS.md"]
    assert source.state == "unsupported"
    assert source.sha256_source is None
    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert str(target) not in rendered


def test_sym_03_broken_symlink_is_refused(tmp_path):
    (tmp_path / "AGENTS.md").symlink_to(tmp_path / "missing.md")

    report = explain_codex(
        tmp_path, cwd=tmp_path, config=resolved_config(tmp_path)
    )

    assert source_map(report)["AGENTS.md"].reason_codes == ("broken_symlink",)


def test_sym_04_symlinked_directory_path_is_unsupported(tmp_path):
    root = tmp_path / "root"
    actual = root / "actual"
    actual.mkdir(parents=True)
    linked = root / "linked"
    linked.symlink_to(actual, target_is_directory=True)

    report = explain_codex(
        root, cwd=linked, config=resolved_config(root)
    )

    assert report.resolution_status == "unsupported"
    assert "path_symlink_unsupported" in {
        item.code for item in report.limitations
    }


def test_sym_05_symlinked_codex_home_is_refused(tmp_path):
    root = tmp_path / "repo"
    real_home = tmp_path / "real-home"
    linked_home = tmp_path / "linked-home"
    root.mkdir()
    real_home.mkdir()
    linked_home.symlink_to(real_home, target_is_directory=True)

    report = explain_codex(
        root,
        cwd=root,
        config=resolved_config(root),
        include_user=True,
        codex_home=linked_home,
    )

    user_scope = next(
        item for item in report.instruction_scopes if item.scope == "user"
    )
    assert user_scope.status == "unsupported"
    assert user_scope.reason_codes == ("path_symlink_unsupported",)


def test_mf_02_project_swap_to_external_symlink_is_not_read(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    candidate = root / "AGENTS.md"
    external_target = tmp_path / "external-secret.md"
    write(candidate, b"original project source")
    write(external_target, b"external sentinel")
    external_hash = hashlib.sha256(b"external sentinel").hexdigest()
    swapped, external_reads, observed_flags = install_swap_before_open(
        monkeypatch, candidate, external_target
    )

    report = explain_codex(
        root, cwd=root, config=resolved_config(root)
    )

    source = source_map(report)["AGENTS.md"]
    assert swapped == [True]
    assert observed_flags[0] & os.O_NOFOLLOW
    assert external_reads == []
    assert source.state == "unsupported"
    assert source.reason_codes == ("unsupported_symlink",)
    assert source.sha256_source is None
    assert "safe_mode_parity_divergence" in {
        item.code for item in report.limitations
    }
    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert external_hash not in rendered


def test_mf_02_user_swap_to_external_symlink_is_not_read(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    home = tmp_path / "codex-home"
    candidate = home / "AGENTS.override.md"
    external_target = tmp_path / "external-user-secret.md"
    root.mkdir()
    write(candidate, b"original user source")
    write(external_target, b"external user sentinel")
    external_hash = hashlib.sha256(b"external user sentinel").hexdigest()
    swapped, external_reads, observed_flags = install_swap_before_open(
        monkeypatch, candidate, external_target
    )

    report = explain_codex(
        root,
        cwd=root,
        config=resolved_config(root),
        include_user=True,
        codex_home=home,
    )

    source = source_map(report)["$CODEX_HOME/AGENTS.override.md"]
    user_scope = next(
        item for item in report.instruction_scopes if item.scope == "user"
    )
    assert swapped == [True]
    assert observed_flags[0] & os.O_NOFOLLOW
    assert external_reads == []
    assert user_scope.status == "unsupported"
    assert source.state == "unsupported"
    assert source.reason_codes == ("unsupported_symlink",)
    assert source.sha256_source is None
    assert "safe_mode_parity_divergence" in {
        item.code for item in report.limitations
    }
    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert external_hash not in rendered


def test_cfg_06_direct_flags_override_snapshot(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "codex_version": "0.1",
                "behavior_profile": "official-contract",
                "platform": "darwin-arm64",
                "selected_profile": None,
                "project_trust": "unknown",
                "effective": {
                    "project_root": str(tmp_path),
                    "project_root_markers": [".git"],
                    "project_doc_fallback_filenames": ["OLD.md"],
                    "project_doc_max_bytes": 10,
                },
                "layers": [
                    {"kind": "cli_override", "status": "not_present"},
                    {"kind": "trusted_project", "status": "not_present"},
                    {"kind": "selected_profile", "status": "not_present"},
                    {"kind": "user", "status": "not_present"},
                    {"kind": "system", "status": "not_present"},
                    {"kind": "defaults", "status": "resolved"},
                ],
            }
        ),
        encoding="utf-8",
    )

    config = build_explain_config(
        snapshot_path=snapshot,
        max_bytes=20,
        fallback_names=["NEW.md"],
    )

    assert config.source == "snapshot_plus_flags"
    assert config.project_doc_max_bytes == 20
    assert config.fallback_filenames == ("NEW.md",)
    assert config.direct_overrides == (
        "project_doc_fallback_filenames",
        "project_doc_max_bytes",
    )


def test_cfg_01_fully_declared_snapshot_has_no_config_limitations(tmp_path):
    config = resolved_config(tmp_path)
    write(tmp_path / "AGENTS.md", b"project")

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    config_codes = {
        "codex_cli_overrides_unknown",
        "profile_not_resolved",
        "user_scope_not_inspected",
        "system_config_unknown",
        "project_config_not_resolved",
        "project_trust_unknown",
        "toml_config_not_parsed",
    }
    assert not config_codes.intersection(
        item.code for item in report.limitations
    )


def test_cfg_02_trusted_project_effective_values_are_applied(tmp_path):
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "project_doc_max_bytes = 1\n", encoding="utf-8"
    )
    write(tmp_path / "AGENTS.md", b"project")
    config = replace(
        resolved_config(tmp_path, max_bytes=7),
        layers=tuple(
            ConfigLayer(
                layer.kind,
                "resolved" if layer.kind == "trusted_project" else layer.status,
            )
            for layer in resolved_config(tmp_path).layers
        ),
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert report.configuration.project_doc_max_bytes == 7
    assert "toml_config_not_parsed" not in {
        item.code for item in report.limitations
    }


def test_cfg_03_untrusted_project_config_is_ignored(tmp_path):
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("model = 'x'\n", encoding="utf-8")
    config = replace(
        resolved_config(tmp_path),
        project_trust="untrusted",
        layers=tuple(
            ConfigLayer(
                layer.kind,
                (
                    "ignored_untrusted"
                    if layer.kind == "trusted_project"
                    else layer.status
                ),
            )
            for layer in resolved_config(tmp_path).layers
        ),
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert "toml_config_not_parsed" not in {
        item.code for item in report.limitations
    }
    assert "project_trust_unknown" not in {
        item.code for item in report.limitations
    }


def test_cfg_04_unknown_project_trust_is_visible(tmp_path):
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("model = 'x'\n", encoding="utf-8")
    config = replace(
        resolved_config(tmp_path),
        project_trust="unknown",
        layers=tuple(
            ConfigLayer(
                layer.kind,
                "unknown" if layer.kind == "trusted_project" else layer.status,
            )
            for layer in resolved_config(tmp_path).layers
        ),
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)
    codes = {item.code for item in report.limitations}

    assert "project_trust_unknown" in codes
    assert "project_config_not_resolved" in codes
    assert "toml_config_not_parsed" in codes


def test_cfg_05_unresolved_selected_profile_is_visible(tmp_path):
    config = replace(
        resolved_config(tmp_path),
        selected_profile="work",
        layers=tuple(
            ConfigLayer(
                layer.kind,
                "unknown" if layer.kind == "selected_profile" else layer.status,
            )
            for layer in resolved_config(tmp_path).layers
        ),
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert "profile_not_resolved" in {
        item.code for item in report.limitations
    }


def test_cfg_07_unknown_future_codex_overrides_are_visible(tmp_path):
    config = replace(
        resolved_config(tmp_path),
        layers=tuple(
            ConfigLayer(
                layer.kind,
                "unknown" if layer.kind == "cli_override" else layer.status,
            )
            for layer in resolved_config(tmp_path).layers
        ),
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert "codex_cli_overrides_unknown" in {
        item.code for item in report.limitations
    }


def test_cfg_08_toml_is_detected_but_not_parsed(tmp_path):
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "project_doc_max_bytes = 1\n", encoding="utf-8"
    )
    config = replace(
        resolved_config(tmp_path),
        project_trust="unknown",
        layers=tuple(
            ConfigLayer(
                layer.kind,
                "unknown" if layer.kind == "trusted_project" else layer.status,
            )
            for layer in resolved_config(tmp_path).layers
        ),
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert report.configuration.project_doc_max_bytes == 32768
    assert "toml_config_not_parsed" in {
        item.code for item in report.limitations
    }


@pytest.mark.parametrize(
    ("profile", "version"),
    [
        ("codex-cli-0.145.0-darwin-arm64", "0.145.0"),
        (
            "codex-cli-0.146.0-alpha.3.1-darwin-arm64",
            "0.146.0-alpha.3.1",
        ),
    ],
)
def test_ver_01_02_exact_profiles_share_observed_matrix(
    tmp_path, profile, version
):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"ROOT1234")
    write(nested / "AGENTS.md", b"NEST5678")
    config = resolved_config(
        tmp_path,
        max_bytes=9,
        profile=profile,
        version=version,
    )

    report = explain_codex(tmp_path, cwd=nested, config=config)

    source = source_map(report)["nested/AGENTS.md"]
    assert source.loaded_bytes == 1
    assert source.evidence_class == "versioned_observation"


def test_ver_03_profile_version_mismatch_is_unknown(tmp_path):
    write(tmp_path / "AGENTS.md", b"project")
    config = resolved_config(
        tmp_path,
        profile=PROFILE,
        version="0.999.0",
    )

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert "codex_version_outside_profile" in {
        item.code for item in report.limitations
    }


def test_ver_03_profile_platform_mismatch_is_unknown(tmp_path):
    nested = tmp_path / "nested"
    write(tmp_path / "AGENTS.md", b"ROOT1234")
    write(nested / "AGENTS.md", b"NEST5678")
    config = resolved_config(
        tmp_path,
        max_bytes=9,
        profile=PROFILE,
        version="0.145.0",
        platform="linux-x64",
    )

    report = explain_codex(tmp_path, cwd=nested, config=config)

    source = source_map(report)["nested/AGENTS.md"]
    assert source.state == "unknown"
    assert source.loaded_bytes is None
    assert "platform_not_validated" in {
        item.code for item in report.limitations
    }


@pytest.mark.parametrize("platform", ["windows-x64", "linux-x64"])
def test_mf_01_official_contract_unvalidated_platform_is_visible(
    tmp_path, platform
):
    config = resolved_config(tmp_path, platform=platform)

    report = explain_codex(tmp_path, cwd=tmp_path, config=config)

    assert report.resolution_status == "resolved_with_limitations"
    assert "platform_not_validated" in {
        item.code for item in report.limitations
    }
    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert "platform_not_validated" in rendered


def test_mf_01_official_contract_validated_darwin_has_no_platform_limit(
    tmp_path,
):
    report = explain_codex(
        tmp_path,
        cwd=tmp_path,
        config=resolved_config(tmp_path, platform="darwin-arm64"),
    )

    assert report.resolution_status == "resolved"
    assert "platform_not_validated" not in {
        item.code for item in report.limitations
    }
    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert "platform_not_validated" not in rendered


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema_version": 2},
        {"schema_version": 1, "effective": "bad"},
        {"schema_version": 1, "unknown": True},
    ],
)
def test_cfg_09_invalid_snapshot_fails_closed(tmp_path, payload):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        build_explain_config(snapshot_path=snapshot)


def test_renderers_expose_same_sources_and_limitations(tmp_path):
    write(tmp_path / "AGENTS.override.md", b"")
    write(tmp_path / "AGENTS.md", b"base")
    report = explain_codex(
        tmp_path, cwd=tmp_path, config=resolved_config(tmp_path)
    )

    for rendered in (
        report.to_json(),
        report.to_terminal(),
        report.to_markdown(),
    ):
        assert "AGENTS.override.md" in rendered
        assert "empty_candidate_retry_unknown" in rendered
        assert "project_empty_candidate_semantics_unverified" in rendered


def test_report_json_ordering_is_deterministic(tmp_path):
    write(tmp_path / "AGENTS.md", b"root")
    config = resolved_config(tmp_path)
    first = explain_codex(tmp_path, cwd=tmp_path, config=config).to_json()
    second = explain_codex(tmp_path, cwd=tmp_path, config=config).to_json()

    assert first == second
    assert json.loads(first)["schema_version"] == 1

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CandidateFact:
    path: Path
    display_path: str
    directory: str
    candidate_kind: str
    is_symlink: bool
    is_regular_file: bool
    source_bytes: int | None


def absolute_lexical(path: str | Path, *, base: Path | None = None) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = (base or Path.cwd()) / value
    return Path(os.path.abspath(os.fspath(value)))


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def relative_display(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    return "." if relative == Path(".") else relative.as_posix()


def path_chain(root: Path, cwd: Path) -> tuple[Path, ...]:
    relative = cwd.relative_to(root)
    result = [root]
    current = root
    for part in relative.parts:
        current = current / part
        result.append(current)
    return tuple(result)


def first_symlink_in_chain(root: Path, cwd: Path) -> Path | None:
    for path in path_chain(root, cwd):
        try:
            if path.is_symlink():
                return path
        except OSError:
            return path
    return None


def first_symlink_component(path: Path) -> Path | None:
    current = Path(path.anchor) if path.is_absolute() else Path()
    for part in path.parts:
        if part == path.anchor:
            continue
        current = current / part
        try:
            if current.is_symlink():
                return current
        except OSError:
            return current
    return None


def is_directory_without_following(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(metadata.st_mode)


def find_root_candidates(
    cwd: Path, markers: Iterable[str]
) -> tuple[Path, ...]:
    marker_names = tuple(markers)
    matches: list[Path] = []
    current = cwd
    while True:
        if any(os.path.lexists(current / marker) for marker in marker_names):
            matches.append(current)
        if current.parent == current:
            break
        current = current.parent
    return tuple(matches)


def inspect_candidate(
    path: Path,
    *,
    display_path: str,
    directory: str,
    candidate_kind: str,
) -> CandidateFact | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    is_symlink = stat.S_ISLNK(metadata.st_mode)
    is_regular = stat.S_ISREG(metadata.st_mode)
    return CandidateFact(
        path=path,
        display_path=display_path,
        directory=directory,
        candidate_kind=candidate_kind,
        is_symlink=is_symlink,
        is_regular_file=is_regular,
        source_bytes=metadata.st_size if is_regular else None,
    )


def read_regular_candidate(fact: CandidateFact) -> bytes:
    if fact.is_symlink or not fact.is_regular_file:
        raise ValueError(f"candidate is not a safe regular file: {fact.path}")
    return fact.path.read_bytes()

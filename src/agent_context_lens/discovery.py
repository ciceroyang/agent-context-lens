from __future__ import annotations

import errno
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
    device: int
    inode: int


class CandidateReadError(Exception):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


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
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


def read_regular_candidate(fact: CandidateFact) -> bytes:
    if fact.is_symlink or not fact.is_regular_file:
        raise CandidateReadError(
            "unsupported_symlink" if fact.is_symlink else "unsupported_file_type",
            f"candidate is not a safe regular file: {fact.path}",
        )

    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise CandidateReadError(
            "safe_no_follow_unavailable",
            "this platform has no no-follow file-open primitive",
        )

    flags = os.O_RDONLY | no_follow
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    flags |= close_on_exec
    try:
        descriptor = os.open(fact.path, flags)
    except OSError as error:
        if error.errno == errno.ELOOP:
            reason_code = "unsupported_symlink"
        elif error.errno == errno.ENOENT:
            reason_code = "candidate_changed_during_read"
        else:
            reason_code = "candidate_open_failed"
        raise CandidateReadError(reason_code, str(error)) from error

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CandidateReadError(
                "unsupported_file_type",
                "opened candidate is not a regular file",
            )
        if (metadata.st_dev, metadata.st_ino) != (fact.device, fact.inode):
            raise CandidateReadError(
                "candidate_changed_during_read",
                "candidate identity changed between inspection and open",
            )

        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except CandidateReadError:
        raise
    except OSError as error:
        raise CandidateReadError("candidate_read_failed", str(error)) from error
    finally:
        os.close(descriptor)

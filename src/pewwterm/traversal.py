"""Recursive directory traversal with loop and permission safeguards.

Algorithm
---------
``walk_directory`` uses an explicit recursive inner function.  Its base cases
stop when the caller's recursion-depth limit or result limit is reached; the
recursive case descends into each eligible subdirectory.  Traversal returns
``Path`` objects and lightweight issues, leaving record construction to
``models.build_file_records`` / ``FileRecord.from_path``.

Loop protection
---------------
Every directory's ``(st_dev, st_ino)`` pair is stored in a ``seen`` set.  If a
directory link points back to an already visited directory the recursion stops
and an issue is recorded.  Links are only followed when
``follow_symlinks=True``; by default a symlink to a directory is listed as a
candidate but is never traversed.  This preserves the browser's explicit-open
policy and makes cyclic links harmless.

Errors
------
An unreadable subdirectory is recorded in ``issues`` and traversal continues.
An invalid root raises ``FileNotFoundError`` / ``NotADirectoryError`` so the UI
can distinguish "empty" from "cannot browse".  An unreadable root becomes an
issue and yields no paths.

Recursive vs iterative
----------------------
A recursive traversal keeps pending directories on the Python call stack; an
iterative traversal uses an explicit stack/list.  Both are O(V+E) for V
directories and E entries.  The recursive form is compact and mirrors the
problem definition; very deep trees risk Python's recursion limit, which is why
``max_depth`` defaults to a modest value.  An iterative version would avoid that
limit at the cost of manual stack bookkeeping.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import config


@dataclass(slots=True)
class WalkIssue:
    """A non-fatal problem encountered while walking."""

    path: Path
    message: str


@dataclass(slots=True)
class TraversalResult:
    """Ordered paths plus diagnostics from a recursive walk."""

    paths: list[Path] = field(default_factory=list)
    issues: list[WalkIssue] = field(default_factory=list)
    truncated: bool = False

    def __iter__(self):
        return iter(self.paths)

    def __len__(self) -> int:
        return len(self.paths)


def _normalise_extensions(extensions: list[str] | tuple[str, ...] | set[str] | None) -> frozenset[str]:
    if not extensions:
        return frozenset()
    normalised = set()
    for extension in extensions:
        value = extension.strip().lower()
        if not value:
            continue
        normalised.add(value if value.startswith(".") else f".{value}")
    return frozenset(normalised)


def walk_directory(
    root: Path | str,
    *,
    filename_filter: str | None = None,
    extensions: list[str] | tuple[str, ...] | set[str] | None = None,
    recursive: bool = True,
    follow_symlinks: bool = False,
    max_depth: int = config.MAX_RECURSIVE_DEPTH,
    max_results: int = config.MAX_RECURSIVE_RESULTS,
) -> TraversalResult:
    """Walk *root* and collect entries matching the optional filters.

    Args:
        root: Directory whose **contents** are traversed (not yielded itself).
        filename_filter: Case-insensitive substring that must appear in the
            entry name.  Applies to files and directories.
        extensions: File extensions such as ``["jpg", ".mp4"]``.  When supplied,
            only regular-file-like entries with those suffixes are collected;
            directories are still traversed but not returned.
        recursive: ``False`` lists one level only.
        follow_symlinks: Opt-in traversal through directory symlinks.
        max_depth: Maximum number of descents below *root* (0 = one level).
        max_results: Hard cap; ``truncated`` is set when reached.

    Returns:
        :class:`TraversalResult` with paths in deterministic name order.

    Raises:
        FileNotFoundError: *root* does not exist.
        NotADirectoryError: *root* is not a directory.
        ValueError: a negative limit was supplied.
    """

    if max_depth < 0 or max_results < 0:
        raise ValueError("max_depth and max_results must be non-negative")

    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(str(root_path))
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))

    needle = (filename_filter or "").strip().casefold()
    wanted_extensions = _normalise_extensions(extensions)
    result = TraversalResult()
    seen: set[tuple[int, int]] = set()

    def include(path: Path, is_dir: bool) -> bool:
        if needle and needle not in path.name.casefold():
            return False
        if wanted_extensions:
            if is_dir:
                return False
            if path.suffix.lower() not in wanted_extensions:
                return False
        return True

    def visit(directory: Path, depth: int) -> None:
        # Base case 1: hard result cap reached.
        if len(result.paths) >= max_results:
            result.truncated = True
            return
        try:
            with os.scandir(directory) as scan:
                entries = sorted(
                    scan,
                    key=lambda entry: (entry.name.casefold(), entry.name),
                )
        except PermissionError as error:
            result.issues.append(WalkIssue(directory, f"permission denied: {error}"))
            return
        except OSError as error:
            result.issues.append(WalkIssue(directory, f"cannot read directory: {error}"))
            return

        for entry in entries:
            if len(result.paths) >= max_results:
                result.truncated = True
                return
            path = Path(entry.path)
            try:
                is_link = entry.is_symlink()
                is_real_dir = entry.is_dir(follow_symlinks=False)
                is_link_dir = is_link and entry.is_dir(follow_symlinks=True)
            except OSError as error:
                result.issues.append(WalkIssue(path, f"cannot inspect: {error}"))
                continue

            is_dir = is_real_dir or is_link_dir
            if include(path, is_dir):
                result.paths.append(path)

            if not recursive or depth >= max_depth:
                continue
            if is_real_dir:
                descend = True
            elif is_link_dir and follow_symlinks:
                descend = True
            else:
                descend = False
            if not descend:
                continue

            try:
                info = path.stat()
            except OSError as error:
                result.issues.append(WalkIssue(path, f"cannot stat link target: {error}"))
                continue
            identity = (info.st_dev, info.st_ino)
            if identity in seen:
                result.issues.append(
                    WalkIssue(path, "already visited; symlink loop or bind mount skipped")
                )
                continue
            seen.add(identity)
            # Recursive case: descend with a lower remaining depth budget.
            visit(path, depth + 1)

    try:
        root_info = root_path.stat()
    except OSError as error:
        result.issues.append(WalkIssue(root_path, f"cannot stat root: {error}"))
        return result
    seen.add((root_info.st_dev, root_info.st_ino))
    visit(root_path, 0)
    return result

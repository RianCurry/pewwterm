"""Filesystem data model and file classification.

The central data structure is a **one-dimensional Python list** of
:class:`FileRecord` objects.  The list is the browser's indexed collection: a
row number is an index into it, iteration renders the table, ``insert`` adds at
a known position and ``pop``/``del`` remove an entry.  Keeping the model as a
plain list makes the linear-search algorithms straightforward and keeps the UI
layer free of ``os.stat`` calls.

Important design decisions:
    * Paths are always :class:`pathlib.Path` objects, never shell strings, so
      spaces and Unicode are handled without quoting.
    * ``classify_path`` raises :class:`OSError` for a path that cannot be
      inspected.  Callers that list a directory decide whether to skip a single
      broken entry or surface the error.
    * Symbolic links are flagged separately.  Classification follows the link
      for display (a link to a directory is shown as a directory), but recursive
      traversal does not follow links unless explicitly asked.

Limitations:
    Size and modification time come from ``stat``.  On unusual filesystems those
    calls can fail (for example a race while a file is deleted); listing skips
    such entries rather than crashing the browser.
"""

from __future__ import annotations

import os
import stat as stat_module
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from . import config


class FileKind(str, Enum):
    """Broad preview categories used by the dispatcher."""

    DIRECTORY = "directory"
    IMAGE = "image"
    VIDEO = "video"
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    CODE = "code"
    OTHER = "other"


KIND_LABELS: dict[FileKind, str] = {
    FileKind.DIRECTORY: "Directory",
    FileKind.IMAGE: "Image",
    FileKind.VIDEO: "Video",
    FileKind.PDF: "PDF",
    FileKind.MARKDOWN: "Markdown",
    FileKind.TEXT: "Text",
    FileKind.CODE: "Code",
    FileKind.OTHER: "File",
}


def kind_from_suffix(suffix: str) -> FileKind:
    """Classify a *regular file* by its lower-case suffix."""

    suffix = suffix.lower()
    if suffix in config.IMAGE_SUFFIXES:
        return FileKind.IMAGE
    if suffix in config.VIDEO_SUFFIXES:
        return FileKind.VIDEO
    if suffix in config.DOCUMENT_SUFFIXES:
        return FileKind.PDF
    if suffix in config.MARKDOWN_SUFFIXES:
        return FileKind.MARKDOWN
    if suffix in config.TEXT_SUFFIXES:
        return FileKind.TEXT
    if suffix in config.CODE_SUFFIXES:
        return FileKind.CODE
    return FileKind.OTHER


def kind_from_mode(mode: int, suffix: str) -> FileKind:
    """Classify from a ``stat`` mode plus a suffix.

    Directories win over suffixes.  Sockets, devices and FIFOs are intentionally
    classified as ``OTHER``; the browser can display them but offers no preview.
    """

    if stat_module.S_ISDIR(mode):
        return FileKind.DIRECTORY
    if stat_module.S_ISREG(mode):
        return kind_from_suffix(suffix)
    return FileKind.OTHER


def classify_path(path: Path | str) -> FileKind:
    """Return the :class:`FileKind` for *path*.

    Raises:
        FileNotFoundError: if the path (or a symlink target) does not exist.
        PermissionError: if metadata cannot be read.
        OSError: for other metadata failures.
    """

    candidate = Path(path)
    info = candidate.stat()
    return kind_from_mode(info.st_mode, candidate.suffix)


def human_size(size: int | None) -> str:
    """Format bytes as a compact base-1024 size (``12.3 KB``).

    ``None`` and negative values render as ``-`` because directories and special
    files do not have a meaningful content size in the browser.
    """

    if size is None or size < 0:
        return "-"
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        value /= 1024.0
        if value < 1024 or unit == "PB":
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"  # pragma: no cover - loop always returns


def format_mtime(timestamp: float | None) -> str:
    """Local timestamp formatted for the narrow MODIFIED table column."""

    if timestamp is None:
        return "-"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "-"


@dataclass(frozen=True, slots=True)
class FileRecord:
    """One row in the browser's one-dimensional list.

    ``kind`` is the preview category, while ``name`` keeps the original name
    (including extension) for display and case-insensitive search.  A directory's
    ``size`` is its directory-entry size, but the UI displays ``-`` for it.
    """

    path: Path
    name: str
    kind: FileKind
    size: int | None
    mtime: float | None
    is_symlink: bool = False
    link_target: str | None = None

    @property
    def suffix(self) -> str:
        """Lower-case extension including the dot, or an empty string."""

        return self.path.suffix.lower()

    @property
    def is_dir(self) -> bool:
        return self.kind is FileKind.DIRECTORY

    @property
    def type_label(self) -> str:
        return KIND_LABELS[self.kind]

    @property
    def display_size(self) -> str:
        return "-" if self.is_dir else human_size(self.size)

    @property
    def display_mtime(self) -> str:
        return format_mtime(self.mtime)

    def equals_path(self, other: Path | str) -> bool:
        """Compare paths without touching the filesystem."""

        return self.path == Path(other)

    @classmethod
    def from_path(cls, path: Path | str) -> "FileRecord":
        """Build a record from ``lstat``/``stat`` information.

        A broken symlink is a valid directory entry.  It is represented as an
        ``OTHER`` record using the link's own metadata rather than raising.

        Raises:
            OSError: if even ``lstat`` fails (for example a deleted entry).
        """

        candidate = Path(path)
        link_info = candidate.lstat()
        is_link = stat_module.S_ISLNK(link_info.st_mode)
        link_target: str | None = None
        if is_link:
            try:
                link_target = str(candidate.readlink())
            except OSError:
                link_target = None
        try:
            info = candidate.stat()  # follows a symlink
            # Preview a link according to its target's extension.  A link named
            # "shortcut" to "photo.jpg" should be treated as an image.
            suffix = candidate.suffix
            if is_link and link_target:
                target_suffix = Path(link_target).suffix
                if target_suffix:
                    suffix = target_suffix
            kind = kind_from_mode(info.st_mode, suffix)
        except OSError:
            info = link_info
            kind = FileKind.OTHER
        size = None if kind is FileKind.DIRECTORY else info.st_size
        return cls(
            path=candidate,
            name=candidate.name or str(candidate),
            kind=kind,
            size=size,
            mtime=info.st_mtime,
            is_symlink=is_link,
            link_target=link_target,
        )


def build_file_records(
    directory: Path | str,
    *,
    include_hidden: bool = True,
    include_symlinks: bool = True,
) -> list[FileRecord]:
    """Read one directory into a one-dimensional list of records.

    Entries are returned in directory order; use :func:`sort_records` for a
    deterministic presentation.  Individual entries that vanish or cannot be
    stat'ed are skipped, but an inaccessible *root* is reported to the caller so
    the UI can show an error state.

    Raises:
        FileNotFoundError: root does not exist.
        NotADirectoryError: root is not a directory.
        PermissionError: root exists but cannot be listed.
        OSError: other listing failures.
    """

    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(str(root))
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    records: list[FileRecord] = []
    with os.scandir(root) as entries:  # failure here is surfaced to the caller
        for entry in entries:
            path = Path(entry.path)
            if not include_hidden and config.is_hidden(path):
                continue
            if entry.is_symlink() and not include_symlinks:
                continue
            try:
                records.append(FileRecord.from_path(path))
            except OSError:
                # A file can disappear between scandir and stat.  One bad entry
                # must not make the whole directory unusable.
                continue
    return records


SORT_KEYS = ("name", "size", "type", "mtime")


def sort_records(
    records: list[FileRecord],
    key: str = "name",
    *,
    reverse: bool = False,
) -> list[FileRecord]:
    """Return a sorted copy of *records*.

    Supported keys are ``name``, ``size``, ``type`` and ``mtime``.  Name and
    type comparisons are case-insensitive.  The original name is the stable
    tie-breaker so equal sizes/timestamps still have predictable order.

    Raises:
        ValueError: for an unknown key (caught by the UI rather than silently
            doing nothing).
    """

    if key not in SORT_KEYS:
        raise ValueError(f"unknown sort key: {key}")

    def sort_key(record: FileRecord) -> tuple:
        folded_name = record.name.casefold()
        if key == "name":
            return (folded_name, record.name)
        if key == "size":
            return (
                record.size if record.size is not None else -1,
                folded_name,
                record.name,
            )
        if key == "type":
            return (record.type_label.casefold(), folded_name, record.name)
        return (
            record.mtime if record.mtime is not None else 0.0,
            folded_name,
            record.name,
        )

    return sorted(records, key=sort_key, reverse=reverse)


def index_of_path(records: list[FileRecord], path: Path | str) -> int | None:
    """Linear index lookup by path; ``None`` if the path is absent."""

    target = Path(path)
    for index, record in enumerate(records):
        if record.path == target:
            return index
    return None


def insert_record(records: list[FileRecord], index: int, record: FileRecord) -> None:
    """Insert a record at *index* (list insertion is O(n))."""

    records.insert(index, record)


def remove_record(records: list[FileRecord], index: int) -> FileRecord:
    """Remove and return the record at *index* (O(n) due to shifting)."""

    return records.pop(index)

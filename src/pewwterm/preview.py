"""Preview dispatcher: turn a :class:`FileRecord` into a renderable description.

This module is deliberately UI-agnostic.  It performs bounded filesystem and
subprocess work in a worker thread and returns a :class:`PreviewResult` made of
plain strings.  The Textual layer decides how to style them (plain Text, ANSI,
Markdown) and never runs blocking work itself.

Dispatch table:

=============  ==========================================================
Kind           Work done here
=============  ==========================================================
directory      first-level entry counts (no recursive size calculation)
image          Pillow metadata + Chafa art or Pillow ASCII fallback
video          FFprobe metadata + FFmpeg still frame + Chafa/ASCII art
pdf            pdftotext first pages + optional pdftoppm page art
markdown       bounded UTF-8 read; UI renders it as Markdown
text / code    bounded UTF-8 read
other          metadata and a helpful unsupported-format message
=============  ==========================================================

Failures are represented by ``notice``/``error`` and never escape as unhandled
exceptions.  A thumbnail is explicitly labelled as a still frame; only
:mod:`pewwterm.player` performs real playback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import document_preview, image_preview, video_preview
from .models import FileKind, FileRecord, human_size
from .player import player_available


@dataclass(slots=True)
class PreviewResult:
    """A plain-data preview ready for the UI to render.

    ``body_format`` is one of ``text``, ``ansi`` or ``markdown``.  The separate
    ``art`` field lets PDF previews show both a page image and extracted text;
    images and videos normally use ``art`` only.
    """

    kind: str
    title: str
    metadata: list[str] = field(default_factory=list)
    body: str = ""
    body_format: str = "text"
    art: str = ""
    art_format: str = "ansi"
    notice: str | None = None
    error: str | None = None
    actions: list[str] = field(default_factory=list)
    record: FileRecord | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


def _base_metadata(record: FileRecord) -> list[str]:
    lines = [
        f"Filename: {record.name}",
        f"Type:     {record.type_label}",
        f"Size:     {record.display_size}",
        f"Modified: {record.display_mtime}",
    ]
    if record.is_symlink:
        target = record.link_target or "unknown target"
        lines.append(f"Symlink:  {target}")
    return lines


def _preview_directory(record: FileRecord) -> PreviewResult:
    directories = 0
    files = 0
    inaccessible = False
    try:
        with os.scandir(record.path) as scan:
            for entry in scan:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        directories += 1
                    else:
                        files += 1
                except OSError:
                    inaccessible = True
    except PermissionError:
        inaccessible = True
    except OSError:
        inaccessible = True

    metadata = _base_metadata(record)
    if inaccessible:
        metadata.append("Contents: unreadable (permission denied)")
        notice = "The directory exists but its contents cannot be listed."
    else:
        metadata.append(f"Contents: {directories} directories, {files} files")
        notice = None
    body = (
        "Directory selected.\n\n"
        "Press Enter to open it. Use Backspace to return to the parent directory."
    )
    return PreviewResult(
        kind="directory",
        title=record.name,
        metadata=metadata,
        body=body,
        notice=notice,
        actions=["Enter: open directory"],
        record=record,
    )


def _preview_image(record: FileRecord, width: int, height: int, cache_root: Path | None) -> PreviewResult:
    probe = image_preview.probe_image(record.path)
    metadata = _base_metadata(record)
    if probe.width and probe.height:
        metadata.append(f"Dimensions: {probe.dimensions}")
    if probe.image_format:
        metadata.append(f"Format:   {probe.image_format}")

    art = image_preview.render_image(record.path, columns=width, rows=height)
    notice = probe.error or art.notice
    if art.notice and probe.error:
        notice = f"{probe.error}. {art.notice}"
    backend = art.backend
    if backend == "pillow-ascii":
        metadata.append("Renderer: ASCII fallback")
    elif backend == "chafa":
        metadata.append("Renderer: chafa ANSI symbols")

    if not art.text and probe.error:
        error = probe.error
    elif not art.text:
        error = "No image renderer produced output"
    else:
        error = None
    return PreviewResult(
        kind="image",
        title=record.name,
        metadata=metadata,
        art=art.text,
        art_format="ansi" if backend == "chafa" else "text",
        notice=notice,
        error=error,
        actions=["Space: refresh preview"],
        record=record,
    )


def _preview_video(record: FileRecord, width: int, height: int, cache_root: Path | None) -> PreviewResult:
    probe = video_probe = video_preview.probe_video(record.path)
    metadata = _base_metadata(record)
    if video_probe.duration is not None:
        metadata.append(f"Duration: {video_probe.duration_text}")
    if video_probe.width and video_probe.height:
        metadata.append(f"Resolution: {video_probe.resolution}")
    if video_probe.codec:
        metadata.append(f"Codec:    {video_probe.codec}")
    if video_probe.container:
        metadata.append(f"Container: {video_probe.container}")
    if video_probe.bit_rate:
        metadata.append(f"Bitrate:  {video_preview.format_bitrate(video_probe.bit_rate)}")

    thumb = video_preview.extract_thumbnail(record.path, cache_root=cache_root)
    art = image_preview.ImageArt()
    notice_parts: list[str] = []
    if probe.error:
        notice_parts.append(probe.error)
    if thumb.error:
        notice_parts.append(thumb.error)
    if thumb.path is not None:
        art = image_preview.render_image(thumb.path, columns=width, rows=height)
        if art.notice:
            notice_parts.append(art.notice)
        metadata.append("Preview:  still frame (not live playback)")
    else:
        metadata.append("Preview:  thumbnail unavailable")
    if not player_available():
        notice_parts.append("mpv is not installed; playback is disabled")
        play_action = "Install mpv to play this video"
    else:
        play_action = "Enter / p: play with mpv"

    error = None
    if not art.text and probe.error:
        error = probe.error
    body = "" if art.text else "No visual thumbnail is available for this video."
    return PreviewResult(
        kind="video",
        title=record.name,
        metadata=metadata,
        body=body,
        art=art.text,
        art_format="ansi" if art.backend == "chafa" else "text",
        notice="; ".join(part for part in notice_parts if part) or None,
        error=error,
        actions=[play_action, "Space: refresh thumbnail"],
        record=record,
    )


def _preview_pdf(record: FileRecord, width: int, height: int, cache_root: Path | None) -> PreviewResult:
    metadata = _base_metadata(record)
    document = document_preview.pdf_text(record.path)
    thumb = document_preview.pdf_thumbnail(record.path, cache_root=cache_root)
    art = image_preview.ImageArt()
    if thumb.path is not None:
        art = image_preview.render_image(thumb.path, columns=width, rows=height)
        metadata.append("Preview:  first page + extracted text")
    elif thumb.error:
        metadata.append("Preview:  extracted text only")

    notices = [
        item
        for item in (document.error, document.notice, thumb.error, art.notice)
        if item
    ]
    body = document.text or "No text could be extracted from this PDF."
    error = None
    if document.error and not document.text and not art.text:
        error = document.error
    return PreviewResult(
        kind="pdf",
        title=record.name,
        metadata=metadata,
        body=body,
        art=art.text,
        art_format="ansi" if art.backend == "chafa" else "text",
        notice="; ".join(notices) or None,
        error=error,
        actions=["Space: refresh preview"],
        record=record,
    )


def _preview_text(record: FileRecord, kind: str) -> PreviewResult:
    document = document_preview.read_text_document(record.path)
    metadata = _base_metadata(record)
    metadata.append("Preview:  source text")
    return PreviewResult(
        kind=kind,
        title=record.name,
        metadata=metadata,
        body=document.text or "The file is empty.",
        body_format="markdown" if kind == "markdown" else "text",
        notice=document.error or document.notice,
        error=document.error,
        actions=["Space: refresh preview"],
        record=record,
    )


def _preview_other(record: FileRecord) -> PreviewResult:
    return PreviewResult(
        kind="other",
        title=record.name,
        metadata=_base_metadata(record),
        body=(
            "No built-in preview for this file type.\n\n"
            "The file remains available to external tools. "
            "Use a file manager or a dedicated application to open it."
        ),
        actions=["No default action"],
        record=record,
    )


def build_preview(
    record: FileRecord,
    width: int = 48,
    height: int = 18,
    *,
    cache_root: Path | str | None = None,
) -> PreviewResult:
    """Dispatch *record* to the correct preview backend.

    This function may block on file I/O or subprocesses; always call it from a
    worker thread (the Textual app uses ``asyncio.to_thread``).  ``width`` and
    ``height`` are character-cell budgets for character art.
    """

    width = max(16, int(width))
    height = max(6, int(height))
    cache = Path(cache_root) if cache_root is not None else None

    if record.kind is FileKind.DIRECTORY:
        return _preview_directory(record)
    if record.kind is FileKind.IMAGE:
        return _preview_image(record, width, height, cache)
    if record.kind is FileKind.VIDEO:
        return _preview_video(record, width, height, cache)
    if record.kind is FileKind.PDF:
        return _preview_pdf(record, width, height, cache)
    if record.kind is FileKind.MARKDOWN:
        return _preview_text(record, "markdown")
    if record.kind is FileKind.TEXT:
        return _preview_text(record, "text")
    if record.kind is FileKind.CODE:
        return _preview_text(record, "code")
    return _preview_other(record)


def error_preview(title: str, message: str) -> PreviewResult:
    """Build a consistent error-state preview for the UI."""

    return PreviewResult(
        kind="error",
        title=title,
        metadata=[],
        body=message,
        error=message,
        actions=["Backspace: return to a readable directory"],
    )


def empty_preview(message: str = "No file selected") -> PreviewResult:
    """Build the empty-selection/no-results state."""

    return PreviewResult(
        kind="empty",
        title="SELECTED MEDIA",
        metadata=[],
        body=message + "\n\nUse Up/Down to select a file; its preview appears here.",
        actions=["Space: refresh preview"],
    )


def file_info_summary(record: FileRecord) -> str:
    """Compact one-line summary used by status bars and tests."""

    return f"{record.name} · {record.type_label} · {human_size(record.size)}"

"""Configuration constants and external-tool discovery for PewwTerm.

PewwTerm deliberately treats multimedia helpers as *optional*.  The TUI remains
usable when ``chafa``, ``ffmpeg``, ``ffprobe``, ``pdftotext``, ``pdftoppm`` or
``mpv`` are absent; the preview layer reports which capability is unavailable
instead of raising an unhandled exception.

Why a separate module?
    Tests can monkeypatch :func:`which` and :func:`cache_dir` without spawning
    real programs or writing to the user's cache.  Application code asks for a
    tool at call time, so installing a tool after startup is picked up on the
    next preview.

Limitations:
    Dependency discovery only checks ``PATH``.  It cannot prove that a decoder,
    fonts or a graphics protocol work in a particular terminal.  Preview code
    still handles subprocess failures defensively.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

APP_NAME = "pewwterm"
APP_TITLE = "PewwTerm"
APP_VERSION = "0.1.0"
PLATFORM_LABEL = "ARCH LINUX"

#: Common image formats understood by Pillow and usually by Chafa.
IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
)

#: Formats for which FFmpeg/FFprobe usually have decoders.  Actual support
#: depends on the installed FFmpeg build.
VIDEO_SUFFIXES: frozenset[str] = frozenset(
    {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".mpg", ".mpeg", ".flv", ".wmv"}
)

DOCUMENT_SUFFIXES: frozenset[str] = frozenset({".pdf"})
MARKDOWN_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown", ".mdown"})
TEXT_SUFFIXES: frozenset[str] = frozenset(
    {".txt", ".log", ".rst", ".csv", ".tsv", ".ini", ".conf", ".toml", ".yaml", ".yml"}
)
CODE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".c", ".h", ".cpp", ".hpp",
        ".rs", ".go", ".java", ".kt", ".sh", ".zsh", ".bash", ".fish", ".lua",
        ".rb", ".php", ".sql", ".css", ".scss", ".html", ".htm", ".xml", ".json",
        ".jsonc", ".tcss", ".vim", ".nix",
    }
)

# Safety limits keep previews and recursive searches bounded.  They are also
# easy to override in tests.
MAX_TEXT_BYTES = 64 * 1024
MAX_TEXT_LINES = 240
MAX_PDF_PAGES = 3
MAX_RECURSIVE_RESULTS = 3000
MAX_RECURSIVE_DEPTH = 24
SUBPROCESS_TIMEOUT = 20.0
THUMBNAIL_WIDTH = 640

#: Ordered tools shown on the help screen.
EXTERNAL_TOOLS: tuple[tuple[str, str], ...] = (
    ("chafa", "image / video / PDF ANSI art"),
    ("ffmpeg", "video thumbnail extraction"),
    ("ffprobe", "video metadata"),
    ("pdftotext", "PDF text extraction"),
    ("pdftoppm", "PDF page thumbnails"),
    ("mpv", "external video playback"),
)

#: Extensions for which a text preview is attempted even if not in a list.
TEXT_SNIFF_BYTES = 4 * 1024


def which(tool: str) -> str | None:
    """Return the absolute path of *tool*, or ``None`` when unavailable.

    Wrapping :func:`shutil.which` gives tests one predictable seam.
    """

    return shutil.which(tool)


def has_tool(tool: str) -> bool:
    """Boolean convenience wrapper around :func:`which`."""

    return which(tool) is not None


def dependency_report() -> dict[str, str | None]:
    """Return ``{tool: path-or-None}`` for every supported external tool."""

    return {tool: which(tool) for tool, _description in EXTERNAL_TOOLS}


def missing_tools(*tools: str) -> list[str]:
    """Return the subset of *tools* that is not currently on ``PATH``."""

    return [tool for tool in tools if not has_tool(tool)]


def lexical_absolute(path: Path | str) -> Path:
    """Return a normalised absolute path *without* resolving symlinks.

    ``Path.resolve`` follows every symlink, which loses the location the user
    actually navigated through.  Using the lexical path keeps entering a
    symlinked directory reversible with Backspace and lets an initial file
    argument match the symlink entry shown in its parent directory.
    """

    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def cache_dir(*, create: bool = True) -> Path:
    """Return the preview cache directory.

    ``PEWWTERM_CACHE_DIR`` takes precedence (useful for tests), followed by the
    XDG cache location.  If the default ``~/.cache`` location is not writable we
    fall back to the system temporary directory so thumbnail generation never
    prevents the file browser from starting.  Explicit overrides are honoured as
    written: if the user points them at an unusable path, the error is surfaced
    by the preview that needed the cache.
    """

    override = os.environ.get("PEWWTERM_CACHE_DIR")
    allow_fallback = False
    if override:
        base = Path(override).expanduser()
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        if xdg:
            base = Path(xdg).expanduser() / APP_NAME
        else:
            allow_fallback = True
            try:
                base = Path.home() / ".cache" / APP_NAME
            except RuntimeError:  # pragma: no cover - unusual container setup
                base = Path(tempfile.gettempdir()) / APP_NAME
                allow_fallback = False
    if create:
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            if not allow_fallback:
                raise
            base = Path(tempfile.gettempdir()) / APP_NAME
            base.mkdir(parents=True, exist_ok=True)
    return base


def is_hidden(path: Path) -> bool:
    """A dotfile is hidden; this intentionally does not inspect parent dirs."""

    return path.name.startswith(".")


def terminal_size(fallback: tuple[int, int] = (100, 32)) -> tuple[int, int]:
    """Best-effort terminal size without touching a running Textual app."""

    size = shutil.get_terminal_size(fallback=fallback)
    return size.columns, size.lines

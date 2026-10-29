"""Image probing and terminal-compatible image rendering.

Two rendering paths are supported:

1. **Chafa symbols** (preferred when installed).  Chafa converts the image to
   ANSI-coloured half/block characters.  We deliberately request ``symbols``
   output with polite mode, relative positioning off and optimisation off.  That
   produces plain ANSI text which Rich can embed inside a Textual widget, without
   requiring Kitty Graphics or Sixel support.
2. **Pillow ASCII fallback** when Chafa is missing or fails.  It preserves the
   aspect ratio approximately (terminal cells are about twice as tall as wide)
   and always works in a UTF-8 monochrome terminal.

Status messages tell the user which path was used.  Corrupt/unsupported images
return an error string rather than raising into the Textual event loop.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(slots=True)
class ImageProbe:
    """Basic image facts obtained without decoding all pixels."""

    width: int | None = None
    height: int | None = None
    image_format: str | None = None
    error: str | None = None

    @property
    def dimensions(self) -> str:
        if self.width is None or self.height is None:
            return "unknown"
        return f"{self.width} x {self.height}"


@dataclass(slots=True)
class ImageArt:
    """Rendered character art plus an explanatory notice."""

    text: str = ""
    notice: str | None = None
    backend: str | None = None


def probe_image(path: Path | str) -> ImageProbe:
    """Read dimensions/format with Pillow, catching corrupt-file errors."""

    candidate = Path(path)
    try:
        from PIL import Image  # imported lazily so a missing Pillow is testable

        with Image.open(candidate) as image:
            return ImageProbe(
                width=image.width,
                height=image.height,
                image_format=(image.format or candidate.suffix.lstrip(".")).upper(),
            )
    except ImportError:
        return ImageProbe(error="Pillow is not installed; image dimensions are unavailable")
    except Exception as error:  # Pillow raises several decoder-specific classes
        return ImageProbe(error=f"Cannot read image: {error}")


def _chafa_art(path: Path, columns: int, rows: int) -> ImageArt:
    executable = config.which("chafa")
    if executable is None:
        return ImageArt(notice="chafa not found; using ASCII fallback")
    command = [
        executable,
        "--format",
        "symbols",
        "--colors",
        "256",
        "--size",
        f"{columns}x{rows}",
        "--animate",
        "off",
        "--relative",
        "off",
        "--polite",
        "on",
        "--probe",
        "off",
        "--optimize",
        "0",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=config.SUBPROCESS_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return ImageArt(notice="chafa disappeared from PATH; using ASCII fallback")
    except subprocess.TimeoutExpired:
        return ImageArt(notice="chafa timed out; using ASCII fallback")
    except OSError as error:
        return ImageArt(notice=f"chafa failed ({error}); using ASCII fallback")
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        message = detail[-1] if detail else f"exit code {completed.returncode}"
        return ImageArt(notice=f"chafa could not render image: {message}")
    art = completed.stdout.rstrip("\n")
    if not art.strip():
        return ImageArt(notice="chafa produced no output; using ASCII fallback")
    return ImageArt(text=art, backend="chafa")


def _pillow_ascii(path: Path, columns: int, rows: int) -> ImageArt:
    try:
        from PIL import Image

        with Image.open(path) as source:
            image = source.convert("RGB")
            width, height = image.size
            if width <= 0 or height <= 0:
                return ImageArt(notice="Image has no drawable pixels")
            # Terminal cells are roughly twice as tall as they are wide.
            target_width = max(8, columns)
            target_height = max(4, min(rows, int(height / width * target_width * 0.5)))
            image = image.resize((target_width, target_height))
            grey = image.convert("L")
            ramp = " .:-=+*#%@"
            pixels = list(grey.tobytes())
            lines = []
            for y in range(target_height):
                row = pixels[y * target_width : (y + 1) * target_width]
                lines.append("".join(ramp[min(len(ramp) - 1, value * len(ramp) // 256)] for value in row))
            return ImageArt(text="\n".join(lines), backend="pillow-ascii")
    except ImportError:
        return ImageArt(notice="Pillow is not installed; no image preview available")
    except Exception as error:
        return ImageArt(notice=f"Cannot build ASCII preview: {error}")


def render_image(path: Path | str, columns: int = 48, rows: int = 18) -> ImageArt:
    """Render *path* as ANSI symbols, falling back to monochrome ASCII.

    Chafa handles transparency and animation reasonably; for animated GIFs only a
    frame is shown.  This is intentionally a still preview, never a claim of live
    playback.  The caller supplies a size derived from the preview panel.
    """

    candidate = Path(path)
    columns = max(8, int(columns))
    rows = max(4, int(rows))
    chafa = _chafa_art(candidate, columns, rows)
    if chafa.text:
        return chafa
    fallback = _pillow_ascii(candidate, columns, rows)
    if fallback.text and chafa.notice:
        fallback.notice = f"{chafa.notice}; {fallback.notice}" if fallback.notice else chafa.notice
    elif fallback.text:
        fallback.notice = chafa.notice
    elif chafa.notice and not fallback.notice:
        fallback.notice = chafa.notice
    return fallback

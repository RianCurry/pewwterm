"""Video metadata and thumbnail extraction through FFprobe/FFmpeg.

External tools are used because writing container demuxers and codec probes in
Python would be enormous and fragile.  Every invocation uses an argument list
(never a shell string), a timeout and captured output.  A missing binary, a
corrupt file or a non-zero exit is converted into a user-facing message.

Thumbnails are still images.  The UI labels them as such and only MPV provides
actual playback.  Generated thumbnails are cached by path + size + mtime so
navigating away and back does not re-run FFmpeg.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(slots=True)
class VideoProbe:
    """Metadata extracted from the first video stream and container."""

    duration: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    container: str | None = None
    bit_rate: int | None = None
    error: str | None = None

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width} x {self.height}"
        return "unknown"

    @property
    def duration_text(self) -> str:
        return format_duration(self.duration)


@dataclass(slots=True)
class ThumbnailResult:
    """Path to a cached JPEG, or an error suitable for the preview panel."""

    path: Path | None = None
    error: str | None = None


def format_duration(seconds: float | None) -> str:
    """Format seconds as ``H:MM:SS`` / ``M:SS``; unknown renders as ``-``."""

    if seconds is None or seconds < 0:
        return "-"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_bitrate(bits_per_second: int | None) -> str:
    if not bits_per_second:
        return "-"
    if bits_per_second >= 1_000_000:
        return f"{bits_per_second / 1_000_000:.1f} Mb/s"
    return f"{bits_per_second / 1000:.0f} kb/s"


def probe_video(path: Path | str) -> VideoProbe:
    """Run ``ffprobe -print_format json`` and parse useful fields.

    The parser is defensive: FFprobe JSON has changed subtly across versions and
    streams may omit optional keys.  Any failure becomes ``VideoProbe.error``.
    """

    candidate = Path(path)
    ffprobe = config.which("ffprobe")
    if ffprobe is None:
        return VideoProbe(error="ffprobe not found; install ffmpeg for video metadata")
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(candidate),
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
        return VideoProbe(error="ffprobe disappeared from PATH")
    except subprocess.TimeoutExpired:
        return VideoProbe(error="ffprobe timed out")
    except OSError as error:
        return VideoProbe(error=f"ffprobe could not start: {error}")
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        message = detail[-1] if detail else f"exit code {completed.returncode}"
        return VideoProbe(error=f"ffprobe failed: {message}")

    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as error:
        return VideoProbe(error=f"ffprobe returned invalid JSON: {error}")

    streams = data.get("streams") or []
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        return VideoProbe(error="No video stream found in this file")

    container = data.get("format") or {}

    def number(value: object) -> float | None:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def integer(value: object) -> int | None:
        try:
            return int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    duration = number(container.get("duration")) or number(video_stream.get("duration"))
    return VideoProbe(
        duration=duration,
        width=integer(video_stream.get("width")),
        height=integer(video_stream.get("height")),
        codec=video_stream.get("codec_name"),
        container=container.get("format_name"),
        bit_rate=integer(container.get("bit_rate")) or integer(video_stream.get("bit_rate")),
    )


def _cache_key(path: Path) -> str:
    try:
        info = path.stat()
        identity = f"{path.resolve()}|{info.st_size}|{info.st_mtime_ns}"
    except OSError:
        identity = str(path)
    return hashlib.sha256(identity.encode("utf-8", "surrogatepass")).hexdigest()[:24]


def extract_thumbnail(
    path: Path | str,
    *,
    cache_root: Path | str | None = None,
    width: int = config.THUMBNAIL_WIDTH,
) -> ThumbnailResult:
    """Create (or reuse) one JPEG frame near the first second of the video.

    A video shorter than one second is retried at timestamp zero.  FFmpeg writes
    to a temporary ``.part.jpg`` and the result is renamed only on success, so a
    killed process cannot leave a truncated cache entry.
    """

    candidate = Path(path)
    ffmpeg = config.which("ffmpeg")
    if ffmpeg is None:
        return ThumbnailResult(error="ffmpeg not found; install ffmpeg for video thumbnails")

    cache_base = Path(cache_root) if cache_root is not None else config.cache_dir()
    output_directory = cache_base / "video"
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return ThumbnailResult(error=f"Cannot create thumbnail cache: {error}")

    output_path = output_directory / f"{_cache_key(candidate)}.jpg"
    if output_path.is_file() and output_path.stat().st_size > 0:
        return ThumbnailResult(path=output_path)

    last_error = "thumbnail extraction failed"
    for seek in ("1", "0"):
        temporary = output_directory / f"{_cache_key(candidate)}-{seek}.part.jpg"
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-ss",
            seek,
            "-i",
            str(candidate),
            "-frames:v",
            "1",
            "-vf",
            f"scale={max(64, width)}:-2",
            "-q:v",
            "3",
            "-y",
            str(temporary),
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
            return ThumbnailResult(error="ffmpeg disappeared from PATH")
        except subprocess.TimeoutExpired:
            last_error = "ffmpeg timed out while creating a thumbnail"
            continue
        except OSError as error:
            return ThumbnailResult(error=f"ffmpeg could not start: {error}")

        if completed.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
            try:
                temporary.replace(output_path)
            except OSError as error:
                return ThumbnailResult(error=f"Cannot store thumbnail: {error}")
            return ThumbnailResult(path=output_path)
        detail = (completed.stderr or "").strip().splitlines()
        last_error = detail[-1] if detail else f"ffmpeg exited with {completed.returncode}"
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return ThumbnailResult(error=f"Cannot create video thumbnail: {last_error}")

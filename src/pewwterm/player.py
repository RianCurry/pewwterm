"""External MPV playback integration.

MPV is launched with an **argument list** (never ``shell=True``).  The Textual
app temporarily suspends its terminal interface around this blocking call, so
MPV owns the screen/window and the TUI is repainted when playback ends.  This is
why the function is synchronous: the suspension context is the correct place to
block, and tests can mock :func:`subprocess.run` deterministically.

``--force-window=yes`` makes audio containers show a window; ``--no-terminal``
keeps MPV from writing over the TUI while it runs.  A user can override extra
arguments through :func:`play_video`'s ``extra_args`` parameter.

Limitations:
    Playback requires a working display/audio stack.  On a headless machine MPV
    may exit non-zero; that is reported, not hidden.  Playback is intentionally
    not embedded in the TUI.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(slots=True)
class PlaybackResult:
    """Outcome of an MPV invocation."""

    ok: bool
    message: str
    returncode: int | None = None


def player_available() -> bool:
    """Whether MPV is currently discoverable on ``PATH``."""

    return config.which("mpv") is not None


def play_video(
    path: Path | str,
    *,
    extra_args: list[str] | None = None,
) -> PlaybackResult:
    """Launch MPV for *path* and wait until it exits.

    The caller should suspend the TUI first.  Missing files, missing MPV,
    process-start failures and non-zero exits all return ``ok=False`` with a
    human-readable message instead of raising.
    """

    candidate = Path(path)
    if not candidate.exists():
        return PlaybackResult(False, f"File not found: {candidate.name}")
    if not candidate.is_file():
        return PlaybackResult(False, "Only regular video files can be played")

    executable = config.which("mpv")
    if executable is None:
        return PlaybackResult(False, "mpv not found; install mpv to play videos")

    command = [
        executable,
        "--really-quiet",
        "--force-window=yes",
        "--no-terminal",
        *(extra_args or []),
        str(candidate),
    ]
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError:
        return PlaybackResult(False, "mpv disappeared from PATH")
    except OSError as error:
        return PlaybackResult(False, f"Cannot start mpv: {error}")
    except KeyboardInterrupt:  # pragma: no cover - depends on interactive signal
        return PlaybackResult(False, "Playback interrupted", returncode=130)
    if completed.returncode != 0:
        return PlaybackResult(
            False,
            f"mpv exited with code {completed.returncode}",
            returncode=completed.returncode,
        )
    return PlaybackResult(True, f"Finished playing {candidate.name}", returncode=0)

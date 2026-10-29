"""Command-line entry point for ``python -m pewwterm`` / ``pewwterm``.

Run ``pewwterm --check`` to print external dependency availability without
starting the TUI.  A file argument opens its parent directory and selects the
file; a directory argument opens that directory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pewwterm",
        description="Multimedia file explorer for the terminal (Arch Linux).",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="directory to open, or a file whose parent directory should open",
    )
    parser.add_argument("--version", action="version", version=f"pewwterm {__version__}")
    parser.add_argument(
        "--check",
        action="store_true",
        help="print optional external dependency status and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.check:
        entries = [
            ("python", sys.executable),
            *[
                (tool, config.which(tool))
                for tool, _description in config.EXTERNAL_TOOLS
            ],
        ]
        for tool, path in entries:
            print(f"{tool:<10} {'available  ' + path if path else 'MISSING'}")
        print(f"cache      {config.cache_dir(create=False)}")
        return 0

    from .app import PewwTermApp

    start = Path(args.directory).expanduser()
    initial_file: Path | None = None
    try:
        if start.is_file():
            initial_file = config.lexical_absolute(start)
            start = initial_file.parent
        else:
            start = config.lexical_absolute(start)
    except OSError:
        start = start.absolute()

    app = PewwTermApp(start, initial_file=initial_file)
    try:
        app.run()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess
    raise SystemExit(main())

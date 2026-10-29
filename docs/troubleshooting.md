# Troubleshooting

## First diagnostic step

Run the dependency report without starting the interface:

```bash
pewwterm --check
```

It prints the Python executable, available external tools and the preview cache
location. A missing tool only reduces the matching capability; it does not
prevent PewwTerm from starting.

## A dependency is listed as MISSING

Install the missing package. On Arch Linux:

```bash
sudo pacman -S --needed chafa ffmpeg poppler mpv
```

`ffmpeg` provides both `ffmpeg` and `ffprobe`. Poppler provides `pdftotext` and
`pdftoppm`.

## Stray characters or unexpected sort changes under tmux

PewwTerm invokes Chafa with `--probe off`. Chafa's default terminal probing waits
for capability replies such as window-size reports, and those replies can
otherwise be consumed as keyboard input. If you maintain a custom build, verify
that the flag is still present in `image_preview.py`.

## Image art looks like monochrome characters

Chafa may be missing, or the terminal may not support the requested colors. The
application falls back to Pillow ASCII. Install Chafa and use a 256-color terminal
with a Unicode-capable font for the full effect.

## Video preview is blank

The video may be corrupt or use a codec not present in the installed FFmpeg
build. PewwTerm shows the metadata and error message instead of a thumbnail. Try
the same file with `ffprobe` and `ffmpeg` directly to confirm decoder support.

## PDF preview has no page image

Install Poppler and confirm both `pdftotext` and `pdftoppm` are available. A
scanned PDF may have no selectable text; the first-page art can still work. An
encrypted or corrupt PDF may fail both paths, in which case the preview reports
the failure.

## Text preview says the file is binary

PewwTerm samples the start of a file for NUL bytes. A file with binary content is
not dumped into the terminal. Use a dedicated tool to inspect it.

## Playback does not start

`mpv` needs a working display and audio stack. It is not embedded in the TUI.
From a headless session, `mpv` may exit non-zero; PewwTerm reports the failure
after returning from suspension. Check that the file is a regular video file and
that `mpv` is on `PATH`.

## Playback refuses with "video files only"

`p` only hands video-classified records to `mpv`; other files get a warning.
Enter opens directories, plays videos, and refreshes the preview for other files.

## Cache problems

Set a writable cache directory:

```bash
export PEWWTERM_CACHE_DIR="$HOME/.cache/pewwterm"
```

Or remove the existing cache to force preview regeneration:

```bash
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/pewwterm"
```

If the default home cache is unwritable, PewwTerm falls back to the system
temporary directory. An explicit `PEWWTERM_CACHE_DIR` or `XDG_CACHE_HOME` is
honoured as written. Preview tools write temporary `.part...` entries and rename
them only on success, so interrupted runs do not leave a truncated cache entry.

## Reporting a bug

Open a bug report with:

- the PewwTerm version (`pewwterm --version`) and Python version,
- terminal emulator and terminal size,
- the exact `pewwterm --check` output,
- steps to reproduce, expected and actual behaviour,
- any traceback or relevant tool error.

Do not include private filenames or file contents. See
[SECURITY.md](../SECURITY.md) for vulnerabilities.

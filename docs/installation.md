# Installation

PewwTerm targets Linux terminals, especially Arch Linux. Python 3.10 or newer is
required.

## Optional system tools

PewwTerm starts without these tools. Install them to enable the corresponding
preview or playback capability.

```bash
sudo pacman -S --needed chafa ffmpeg poppler mpv
```

| Tool | Used for | Without it |
| --- | --- | --- |
| `chafa` | ANSI image, video-frame and PDF-page art | Pillow ASCII fallback where possible |
| `ffmpeg` | Video still frames | Video metadata only, no thumbnail |
| `ffprobe` | Video duration, resolution, codec and bitrate | Preview without video metadata |
| `pdftotext` | PDF text extraction | First-page art only, if `pdftoppm` is available |
| `pdftoppm` | PDF first-page thumbnails | Extracted text only |
| `mpv` | Actual video playback | `p` and Enter report that playback is disabled |

A 256-color terminal and a Unicode-capable font are recommended for Chafa output.

## Install from a checkout

```bash
cd pewwterm
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Install development tools

```bash
python -m pip install -e '.[dev]'
```

The `dev` extra installs pytest, pytest-asyncio and Ruff.

## Verify the installation

Print the Python version, cache location and availability of every external
tool without opening the interface:

```bash
pewwterm --check
```

The same command is available through the module entry point:

```bash
python -m pewwterm --check
```

## Run

```bash
pewwterm                      # current directory
pewwterm ~/Videos             # a directory
pewwterm ~/Videos/clip.mp4    # parent directory, with the file selected
pewwterm --version
```

Symlinked files and directories keep the path you passed to the command, so
parent navigation behaves relative to that location.

## Update or remove

Reinstall editable changes from the checkout:

```bash
source .venv/bin/activate
python -m pip install -e .
```

Remove the environment by deleting `.venv`. Remove cached preview files by
deleting the directory reported by `pewwterm --check`.

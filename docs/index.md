# PewwTerm documentation

PewwTerm is a read-only, keyboard-driven multimedia file explorer for the
terminal. It browses directories, previews images, videos, PDFs, Markdown and
source code, and hands videos to `mpv` for playback.

The [project README](../README.md) is the quick overview and includes the current
screenshot gallery.

## Guides

| Guide | Contents |
| --- | --- |
| [Installation](installation.md) | Requirements, Arch packages, virtual environment, dependency check |
| [Usage](usage.md) | Launching, navigation, search, sorting, playback and responsive layout |
| [Previews](previews.md) | Image, video, PDF and text previews, cache and fallback behaviour |
| [Architecture](architecture.md) | Module map, worker model, traversal safeguards and external calls |
| [Development](development.md) | Test suite, linting, screenshot generation and contribution workflow |
| [Troubleshooting](troubleshooting.md) | Missing tools, blank previews, playback and cache problems |

## Project files

- [Contributing guide](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [License](../LICENSE)
- [Issue templates](../.github/ISSUE_TEMPLATE)
- [Test workflow](../.github/workflows/tests.yml)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pewwterm --check
pewwterm
```

PewwTerm is designed for Linux terminals, especially Arch Linux. It requires
Python 3.10 or newer and works without the optional multimedia tools, with a
reduced preview capability.

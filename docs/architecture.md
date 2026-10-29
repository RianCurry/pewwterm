# Architecture

PewwTerm keeps filesystem, search, traversal, preview and UI concerns in small
modules with tests around each boundary.

## Module map

| Module | Responsibility |
| --- | --- |
| [`__main__.py`](../src/pewwterm/__main__.py) | CLI parsing, `--check`, `--version`, starting the app |
| [`app.py`](../src/pewwterm/app.py) | Textual UI, bindings, workers, responsive layout |
| [`config.py`](../src/pewwterm/config.py) | Constants, optional-tool discovery, cache location |
| [`models.py`](../src/pewwterm/models.py) | `FileRecord`, classification, formatting, sorting |
| [`search.py`](../src/pewwterm/search.py) | Linear partial search and binary exact search |
| [`traversal.py`](../src/pewwterm/traversal.py) | Recursive walk with depth, result and loop safeguards |
| [`image_preview.py`](../src/pewwterm/image_preview.py) | Chafa rendering, Pillow metadata and ASCII fallback |
| [`video_preview.py`](../src/pewwterm/video_preview.py) | FFprobe metadata and cached FFmpeg still frames |
| [`document_preview.py`](../src/pewwterm/document_preview.py) | Bounded text, `pdftotext` and `pdftoppm` helpers |
| [`player.py`](../src/pewwterm/player.py) | External `mpv` invocation and result reporting |
| [`preview.py`](../src/pewwterm/preview.py) | UI-agnostic preview dispatcher and result model |

Tests live in [`tests/`](../tests), and
[`demo/capture_screens.py`](../demo/capture_screens.py) renders deterministic SVG
screenshots through Textual's test driver.

## Data model

The browser stores its current rows as a single `list[FileRecord]`. A table row
index is an index into that list. Directory records and search result records are
kept separately so sorting can update both.

`FileRecord.from_path` uses `lstat` to detect symlinks and `stat` to classify the
target. A broken symlink remains a valid `OTHER` entry. The traversal API can
opt in to following directory symlinks, but the application passes
`follow_symlinks=False` and lists them without descending into them.

Paths are lexical absolute paths rather than fully resolved paths. This preserves
the directory the user actually navigated through: entering a symlinked directory
and pressing Backspace returns to the directory containing the link. Preview
cache keys still resolve paths so different links to the same file share cached
art.

## UI and workers

Preview work and recursive search run in exclusive Textual workers backed by
`asyncio.to_thread`. A monotonic token is captured when a worker starts; when it
finishes, a result is rendered only if its token still matches the latest
selection. This prevents a slow preview for an old file from replacing a newer
one.

Search is debounced. In non-recursive mode, filtering is immediate over the
in-memory record list. In recursive mode, a delayed background traversal starts
after typing pauses. Query changes invalidate pending results, and leaving search
cancels timers and invalidates in-flight work.

The preview panel is hidden below `96` columns. Resizing back to the split layout
starts a fresh preview for the current selection.

## Traversal safeguards

Recursive traversal uses a `(st_dev, st_ino)` visited set. The application lists
directory symlinks but does not follow them; the traversal API also supports an
explicit opt-in for callers that need it. When following is enabled, a link back
to an already visited directory is recorded as an issue and skipped. Traversal
is bounded to depth 24 and 3000 results, and unreadable subdirectories do not
abort the whole search.

## External processes

`chafa`, `ffmpeg`, `ffprobe`, `pdftotext`, `pdftoppm` and `mpv` are optional.
Calls use argument lists, no shell, captured output where appropriate, and a
timeout for bounded operations. Failures become `notice` or `error` fields in a
preview or a `PlaybackResult`; they never replace the interface with a traceback.

`mpv` is the exception to captured output: the app suspends the terminal, hands
the display to `mpv`, waits for it to exit, then resumes and repaints. The player
function is synchronous precisely because the suspension context is the correct
place to block.

## Testing strategy

Unit tests cover classification, formatting, search algorithms, traversal loops
and limits, preview dispatch, external-tool failures, cache behaviour and MPV
argument construction. Textual integration tests use a fake preview builder for
determinism and the real text preview path where useful. External subprocess
tests use temporary files and mocked `subprocess.run` calls.

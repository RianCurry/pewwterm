# Usage

PewwTerm is a file browser, not a shell replacement. It never copies, moves,
renames or deletes files. Video playback is delegated to an external `mpv`
process.

## Launching

```bash
pewwterm                      # current directory
pewwterm ~/Downloads          # open a directory
pewwterm ~/Downloads/clip.mp4 # open the parent and select the file
pewwterm --check              # dependency report
pewwterm --version
```

## Layout

The upper area shows the current location. The main area is a split view with a
file table on the left and a preview on the right. Below `96` terminal columns
the preview is hidden and the file table expands to the full width. The status
bar shows item counts, the selected name, search state and sort order.

The file list is one-dimensional. Up and Down move through the current rows;
search results replace the rows rather than opening a separate output view.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Up` / `Down` | Move the file selection |
| `Enter` | Open a directory, play a video, or refresh a file preview |
| `Backspace` | Go to the parent directory |
| `Space` | Reload the selected file's preview |
| `/` | Open search in the current directory, or recursively when enabled |
| `type` | Case-insensitive partial filename matching |
| `Up` / `Down` in search | Select a search result while the query keeps focus |
| `Enter` in search | Open the selected result |
| `Esc` | Clear the query; press again to close search |
| `r` | Toggle recursive search before opening the search box |
| `Ctrl+R` | Toggle recursive search while typing and rerun the query |
| `1` | Sort by name |
| `2` | Sort by size |
| `3` | Sort by type |
| `4` | Sort by modification time |
| `o` | Reverse the current sort order |
| `p` | Play the selected video with `mpv` |
| `?` | Show keyboard and dependency help |
| `q` / `Ctrl+Q` | Quit |

Inside the search box, printable keys are query text. Recursive search is
therefore also bound to `Ctrl+R` while typing, so the letter `r` remains usable
in filenames. Opening search preserves the current selection. Escaping out of
search restores the directory listing and focuses the file table.

## Search

Without recursion, typing filters the current directory's records with a
case-insensitive substring match on the filename. With recursion enabled, the
search walks subdirectories in a background worker and shows relative paths for
nested matches.

Recursive search is bounded to depth 24 and 3000 results. Symlinked directories
can appear as matches, but their contents are not traversed. Unreadable or
disappearing entries are recorded as traversal issues and shown as a short note
instead of failing the whole search.

## Sorting

Sorting is stable and case-insensitive for name and type comparisons. The exact
filename is the tie-breaker, so names that differ only by case keep a predictable
order. Sorting a directory listing preserves the selected file. Press the same
sort key again to reapply it, or `o` to reverse the current order.

## Playback

Pressing Enter or `p` on a video suspends the Textual interface and starts `mpv`
with an argument list. After playback exits, the interface is repainted and the
result is reported. Non-video files are rejected with a warning. If `mpv` is not
installed, the preview panel explains how to enable playback.

`mpv` needs a working display and audio stack. Playback is not embedded in the
TUI, and the preview shown before playback is a still frame.

## Error and empty states

A missing, unreadable or non-directory path produces an error status and an error
preview instead of an empty file list. Empty directories and searches with no
matches show an explanatory message. Sorting or opening search does not hide an
active directory error; return to a readable directory with Backspace or by
quitting.

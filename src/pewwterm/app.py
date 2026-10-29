"""Textual user interface for PewwTerm.

Layout
------
A one-line brand bar, a location panel, a responsive split body (file table +
preview), a status bar and a fixed key-hint bar.  Below 96 terminal columns the
preview panel is hidden and the file table expands to the full width; this keeps
the browser usable on 80x24 terminals instead of letting the preview consume the
screen.

Interaction and state
---------------------
The file table is a :class:`~textual.widgets.DataTable` whose row index maps
directly to ``self._display_records`` — a one-dimensional list of
:class:`~pewwterm.models.FileRecord`.  Search reuses the same table, so results
are genuinely selectable rather than printed text.  The current directory's
records and the visible search results are kept separately; sorting re-sorts both.

Blocking work (FFmpeg thumbnails, Poppler extraction, large recursive walks) is
offloaded with Textual workers and ``asyncio.to_thread``.  Preview/search workers
are *exclusive*: when the selection changes, the previous worker is cancelled and
its result ignored via a monotonically increasing token.  The UI therefore stays
responsive while a thumbnail is generated.

Why MPV suspends the app
------------------------
MPV is an external player, not an embedded video widget.  The app suspends its
terminal driver around the blocking player call and resumes afterwards, which is
the safe way to hand the terminal/display to another program.  The preview shown
before playback is a still frame and is labelled as such.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from . import config
from .models import (
    FileKind,
    FileRecord,
    build_file_records,
    index_of_path,
    sort_records,
)
from .player import PlaybackResult, play_video, player_available
from .preview import (
    PreviewResult,
    build_preview,
    empty_preview,
    error_preview,
)
from .search import linear_search
from .traversal import TraversalResult, walk_directory

MIN_PREVIEW_WIDTH = 96
PREVIEW_DEBOUNCE = 0.12
SEARCH_DEBOUNCE = 0.22


class HelpScreen(ModalScreen[None]):
    """Scrollable keyboard/dependency reference."""

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=False),
        Binding("q", "dismiss_help", "Close", show=False),
        Binding("question_mark", "dismiss_help", "Close", show=False),
        Binding("up", "scroll_up", "Scroll up", show=False),
        Binding("down", "scroll_down", "Scroll down", show=False),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
        background: #000000 55%;
    }
    #help-dialog {
        width: 92%;
        max-width: 84;
        height: 88%;
        border: round #3a6b4f;
        background: #0b120e;
        padding: 1 2;
    }
    #help-scroll {
        height: 1fr;
        scrollbar-color: #2d4d3a;
    }
    #help-body {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._body = self._build_text()

    @staticmethod
    def _build_text() -> Text:
        dependencies = config.dependency_report()
        dep_lines = []
        for tool, purpose in config.EXTERNAL_TOOLS:
            path = dependencies.get(tool)
            status = "available" if path else "MISSING"
            dep_lines.append(f"  {tool:<10} {status:<10} {purpose}")
        text = Text()
        text.append("PEWWTERM · KEYBOARD HELP\n", style="bold #7ee2a8")
        text.append("A multimedia file explorer, not a shell replacement.\n\n", style="#6f8076")
        sections = [
            (
                "NAVIGATION",
                [
                    ("Up / Down", "Move the file selection"),
                    ("Enter", "Open directory, play video, or refresh preview"),
                    ("Backspace", "Go to the parent directory"),
                    ("Space", "Refresh preview for the selected file"),
                ],
            ),
            (
                "SEARCH",
                [
                    ("/", "Open the search box (current directory, or recursive)"),
                    ("type", "Case-insensitive partial filename matching"),
                    ("Up / Down", "Select a search result (works while typing)"),
                    ("Enter", "Open the selected result"),
                    ("Esc", "Clear the query; press again to close search"),
                    ("r", "Toggle recursive search before opening the box"),
                    ("Ctrl+R", "Toggle recursive search while typing and rerun"),
                ],
            ),
            (
                "VIEW AND SORT",
                [
                    ("1", "Sort by name"),
                    ("2", "Sort by size"),
                    ("3", "Sort by type"),
                    ("4", "Sort by modification time"),
                    ("o", "Reverse the current sort order"),
                    ("Space", "Reload the preview of the selected file"),
                    ("p", "Play the selected video with mpv"),
                    ("?", "Show this help"),
                    ("q / Ctrl+Q", "Quit PewwTerm"),
                ],
            ),
        ]
        for heading, rows in sections:
            text.append(f"{heading}\n", style="bold #a8d8bb")
            for keys, description in rows:
                text.append(f"  {keys:<14}", style="#7ee2a8")
                text.append(f"{description}\n", style="#b9c6bd")
            text.append("\n")

        text.append("PREVIEW BEHAVIOUR\n", style="bold #a8d8bb")
        preview_lines = [
            "  Images:   chafa ANSI symbols when available, otherwise Pillow ASCII.",
            "  Videos:   FFmpeg still frame + metadata; Enter/p launches mpv.",
            "  PDFs:     pdftotext text plus optional pdftoppm first-page art.",
            "  Text/MD:  bounded UTF-8 read (larger files are truncated).",
            "  Other:    metadata and available actions are shown.",
            f"  Narrow terminals below {MIN_PREVIEW_WIDTH} columns hide the preview panel.",
            "  Long thumbnail/PDF operations run in background workers.",
        ]
        for line in preview_lines:
            text.append(line + "\n", style="#b9c6bd")
        text.append("\nEXTERNAL DEPENDENCIES (checked now)\n", style="bold #a8d8bb")
        for line in dep_lines:
            unavailable = "MISSING" in line
            text.append(line + "\n", style="#d6b36a" if unavailable else "#8fa096")
        text.append(
            "\nOptional tools degrade gracefully: a missing helper produces a message "
            "in the preview panel, never a crash.\n",
            style="#6f8076",
        )
        return text

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            with VerticalScroll(id="help-scroll"):
                yield Static(self._body, id="help-body")

    def on_mount(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).focus()

    def action_dismiss_help(self) -> None:
        self.dismiss(None)

    def action_scroll_up(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_down(animate=False)

    def action_page_up(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_page_down(animate=False)


class PewwTermApp(App[None]):
    """The main PewwTerm application."""

    TITLE = config.APP_TITLE
    SUB_TITLE = config.PLATFORM_LABEL

    CSS = """
    Screen {
        background: #080b09;
        color: #c7d2ca;
    }
    #topbar {
        height: 1;
        background: #0e1511;
        padding: 0 1;
    }
    #brand {
        width: 1fr;
        color: #7ee2a8;
        text-style: bold;
    }
    #platform {
        width: auto;
        color: #58695f;
    }
    #location {
        height: 4;
        border: round #223129;
        background: #0a0f0c;
        padding: 0 1;
    }
    #main-body {
        height: 1fr;
    }
    #files-panel {
        width: 56%;
        border: round #223129;
        background: #080b09;
    }
    #files-panel.full {
        width: 100%;
    }
    #preview-panel {
        width: 44%;
        border: round #223129;
        background: #0a0f0c;
        padding: 0 1;
        scrollbar-color: #2d4d3a;
    }
    DataTable {
        height: 1fr;
        background: #080b09;
        color: #b9c6bd;
        scrollbar-color: #2d4d3a;
    }
    DataTable > .datatable--header {
        background: #0e1511;
        color: #7ee2a8;
        text-style: bold;
    }
    DataTable > .datatable--cursor {
        background: #153421;
        color: #a7f3c4;
    }
    DataTable > .datatable--hover {
        background: #112018;
    }
    #empty-state {
        height: 1fr;
        content-align: center middle;
        color: #5f7166;
    }
    #search-box {
        height: auto;
        display: none;
        border-top: solid #1d2b23;
        background: #0b120e;
        padding: 0 1;
    }
    #search-box.active {
        display: block;
    }
    #search-input {
        height: 1;
        border: none;
        background: #0d1611;
        color: #e4eee7;
    }
    #search-input:focus {
        background: #0d1611;
    }
    #search-hint {
        height: 1;
        color: #5f7166;
    }
    #preview-content {
        width: 100%;
        height: auto;
    }
    #statusbar {
        height: 1;
        background: #0e1511;
        color: #9fb0a5;
        padding: 0 1;
    }
    #keyhints {
        height: 1;
        background: #0e1511;
        color: #5f7166;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "open_selected", "Open", show=False),
        Binding("space", "preview_selected", "Preview", show=False),
        Binding("slash", "search", "Search", show=False),
        Binding("escape", "escape", "Close/Clear", show=False),
        Binding("backspace", "parent", "Parent", show=False),
        Binding("r", "toggle_recursive", "Recursive", show=False),
        Binding("ctrl+r", "toggle_recursive", "Recursive", show=False, priority=True),
        Binding("question_mark", "help", "Help", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False, priority=True),
        Binding("p", "play_selected", "Play", show=False),
        Binding("1", "sort_name", "Sort name", show=False),
        Binding("2", "sort_size", "Sort size", show=False),
        Binding("3", "sort_type", "Sort type", show=False),
        Binding("4", "sort_mtime", "Sort modified", show=False),
        Binding("o", "toggle_order", "Order", show=False),
    ]

    def __init__(
        self,
        start_path: Path | str | None = None,
        *,
        initial_file: Path | str | None = None,
        preview_builder=build_preview,
        player=play_video,
    ) -> None:
        super().__init__()
        self.start_path = Path(start_path).expanduser() if start_path else Path.cwd()
        self.initial_file = Path(initial_file).expanduser() if initial_file else None
        self._preview_builder = preview_builder
        self._player = player

        self.current_dir: Path = self.start_path
        self._all_records: list[FileRecord] = []
        self._display_records: list[FileRecord] = []
        self._recursive_results: list[FileRecord] | None = None
        self._selected_index = 0
        self._error: str | None = None

        self._sort_key = "name"
        self._sort_reverse = False
        self._recursive = False

        self._search_active = False
        self._search_query = ""
        self._search_note = ""
        self._search_busy = False
        self._search_token = 0
        self._search_timer = None

        self._preview_token = 0
        self._preview_visible = True
        self._last_preview: PreviewResult | None = None

    # ------------------------------------------------------------------ compose
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(config.APP_NAME, id="brand")
            yield Static(config.PLATFORM_LABEL, id="platform")
        yield Static(id="location")
        with Horizontal(id="main-body"):
            with Vertical(id="files-panel"):
                yield DataTable(id="files")
                yield Static(
                    "No files to display.",
                    id="empty-state",
                    markup=False,
                )
                with Vertical(id="search-box"):
                    yield Input(placeholder="Search filenames…", id="search-input")
                    yield Static(id="search-hint")
            with VerticalScroll(id="preview-panel"):
                yield Static(id="preview-content")
        yield Static(id="statusbar")
        yield Static(
            "Up/Down Navigate · Enter Open · Space Preview · / Search · "
            "Bksp Parent · r Recursive · 1-4 Sort · ? Help · q Quit",
            id="keyhints",
            markup=False,
        )

    # ------------------------------------------------------------------ startup
    def on_mount(self) -> None:
        table = self.query_one("#files", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("NAME", key="name")
        table.add_column("TYPE", key="type", width=10)
        table.add_column("SIZE", key="size", width=9)
        table.add_column("MODIFIED", key="mtime", width=16)

        self.query_one("#files-panel", Vertical).border_title = "FILES"
        self.query_one("#preview-panel", VerticalScroll).border_title = "PREVIEW"

        self._apply_responsive(self.size.width or 100)
        target = self.start_path
        select_path = self.initial_file
        if target.exists() and target.is_file():
            select_path = target
            target = target.parent
        self._navigate(target, select_path=select_path)

    def on_resize(self, event: events.Resize) -> None:
        self._apply_responsive(event.size.width)

    def _apply_responsive(self, width: int) -> None:
        try:
            panel = self.query_one("#preview-panel", VerticalScroll)
            files_panel = self.query_one("#files-panel", Vertical)
        except Exception:
            return
        visible = width >= MIN_PREVIEW_WIDTH
        was_visible = self._preview_visible
        self._preview_visible = visible
        panel.display = visible
        files_panel.set_class(not visible, "full")
        if visible and not was_visible:
            record = self._current_record()
            if record is not None:
                self._start_preview(record, force=True)
        self._update_status()

    # --------------------------------------------------------------- navigation
    def _navigate(self, target: Path | str, *, select_path: Path | str | None = None) -> None:
        self._deactivate_search(restore=False)
        candidate = Path(target).expanduser()
        try:
            candidate = config.lexical_absolute(candidate)
        except OSError:
            candidate = candidate.absolute()
        self.current_dir = candidate
        if select_path is not None:
            try:
                select_path = config.lexical_absolute(select_path)
            except OSError:
                select_path = Path(select_path).absolute()
        self._error = None
        try:
            records = build_file_records(candidate)
        except PermissionError:
            self._error = f"Permission denied: {candidate}"
            records = []
        except FileNotFoundError:
            self._error = f"Directory not found: {candidate}"
            records = []
        except NotADirectoryError:
            self._error = f"Not a directory: {candidate}"
            records = []
        except OSError as error:
            self._error = f"Cannot open {candidate}: {error}"
            records = []

        self._all_records = sort_records(records, self._sort_key, reverse=self._sort_reverse)
        self._update_location()
        if self._error:
            self._set_display_records([], empty_message=self._error)
            self._preview_token += 1
            self._render_preview(error_preview("CANNOT OPEN", self._error))
            self._update_status()
            return

        empty_message = "This directory is empty."
        self._set_display_records(
            self._all_records,
            empty_message=empty_message,
            select_path=select_path,
        )
        try:
            self.query_one("#files", DataTable).focus()
        except Exception:
            pass
        self._update_status()

    def _update_location(self) -> None:
        display = str(self.current_dir)
        try:
            home = Path.home()
            if self.current_dir == home:
                display = "~"
            elif home in self.current_dir.parents:
                display = f"~/{self.current_dir.relative_to(home)}"
        except (RuntimeError, ValueError):
            pass
        path_style = "bold #ff9b90" if self._error else "bold #e4eee7"
        self.query_one("#location", Static).update(
            Text.assemble(("LOCATION\n", "#5f7166"), (display, path_style))
        )

    # ---------------------------------------------------------------- file table
    def _set_display_records(
        self,
        records: list[FileRecord],
        *,
        empty_message: str = "No files to display.",
        select_path: Path | str | None = None,
    ) -> None:
        self._display_records = list(records)
        table = self.query_one("#files", DataTable)
        empty = self.query_one("#empty-state", Static)
        table.clear(columns=False)
        for row_index, record in enumerate(self._display_records):
            table.add_row(
                self._table_name(record),
                Text(record.type_label, style="#8b9a91"),
                Text(record.display_size, style="#8b9a91", justify="right"),
                Text(record.display_mtime, style="#73837a"),
                key=str(row_index),
            )

        if not self._display_records:
            table.display = False
            empty.display = True
            empty.update(Text(empty_message, style="#6f8076", justify="center"))
            self._selected_index = 0
            self._preview_token += 1
            self._render_preview(empty_preview(empty_message))
            self._update_status()
            return

        table.display = True
        empty.display = False
        index = 0
        if select_path is not None:
            found = index_of_path(self._display_records, select_path)
            if found is not None:
                index = found
        table.move_cursor(row=index, animate=False)
        self._update_selection(index)

    def _table_name(self, record: FileRecord) -> Text:
        name = record.name
        if self._search_active and record.path.parent != self.current_dir:
            try:
                name = str(record.path.relative_to(self.current_dir))
            except ValueError:
                name = str(record.path)
        if record.is_dir and not name.endswith("/"):
            name += "/"
        if record.is_symlink:
            name = "↳ " + name
        style = "#9be8bb" if record.is_dir else "#cdd8d1"
        return Text(name, style=style)

    def _current_record(self) -> FileRecord | None:
        if 0 <= self._selected_index < len(self._display_records):
            return self._display_records[self._selected_index]
        return None

    def _update_selection(self, index: int) -> None:
        self._selected_index = index
        self._update_status()
        record = self._current_record()
        if record is None:
            self._preview_token += 1
            self._render_preview(empty_preview())
            return
        if self._preview_visible:
            self._start_preview(record)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "files":
            return
        if 0 <= event.cursor_row < len(self._display_records):
            self._update_selection(event.cursor_row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "files":
            self._open_selected()

    # ----------------------------------------------------------------- preview
    def _preview_size(self) -> tuple[int, int]:
        try:
            panel = self.query_one("#preview-panel", VerticalScroll)
            width = max(24, min(78, panel.size.width - 4))
            height = max(8, min(22, panel.size.height - 11))
            return width, height
        except Exception:
            return 48, 16

    def _start_preview(self, record: FileRecord, *, force: bool = False) -> None:
        if not force and not self._preview_visible:
            return
        self._preview_token += 1
        token = self._preview_token
        width, height = self._preview_size()
        self.query_one("#preview-content", Static).update(
            Text(
                f"Loading preview…\n\n{record.name}",
                style="#6f8076",
                justify="center",
            )
        )
        try:
            self.query_one("#preview-panel", VerticalScroll).scroll_home(animate=False)
        except Exception:
            pass
        self._preview_worker(token, record, width, height)

    @work(exclusive=True, group="preview")
    async def _preview_worker(
        self,
        token: int,
        record: FileRecord,
        width: int,
        height: int,
    ) -> None:
        try:
            result = await asyncio.to_thread(
                self._preview_builder,
                record,
                width,
                height,
            )
        except Exception as error:  # a broken backend must not crash the TUI
            result = error_preview(record.name, f"Preview failed: {error}")
        if token != self._preview_token:
            return
        self._render_preview(result)

    def _render_preview(self, result: PreviewResult) -> None:
        self._last_preview = result
        parts: list[object] = []
        accent = "#ff9b90" if result.is_error else "#a8f0c2"
        parts.append(Text(result.title, style=f"bold {accent}"))
        if result.metadata:
            parts.append(Text("\n" + "\n".join(result.metadata), style="#8fa096"))
        if result.notice:
            parts.append(Text("\n" + result.notice, style="italic #d6b36a"))
        if result.art:
            parts.append(Text("\n"))
            if result.art_format == "ansi":
                parts.append(Text.from_ansi(result.art, no_wrap=True))
            else:
                parts.append(Text(result.art, style="#80938a", no_wrap=True))
        if result.body:
            parts.append(Text("\n"))
            if result.body_format == "markdown":
                parts.append(Markdown(result.body))
            else:
                parts.append(Text(result.body, style="#b9c6bd"))
        if result.error and result.body_format != "text":
            parts.append(Text("\n" + result.error, style="#ff9b90"))
        elif result.error and result.error not in result.body:
            parts.append(Text("\n" + result.error, style="#ff9b90"))
        if result.actions:
            parts.append(Text("\n\n" + "  ·  ".join(result.actions), style="#5f7166"))

        self.query_one("#preview-content", Static).update(Group(*parts))
        try:
            self.query_one("#preview-panel", VerticalScroll).scroll_home(animate=False)
        except Exception:
            pass
        self._update_status()

    # ------------------------------------------------------------------ search
    def _search_input(self) -> Input:
        return self.query_one("#search-input", Input)

    def _update_search_hint(self) -> None:
        try:
            hint = self.query_one("#search-hint", Static)
        except Exception:
            return
        if not self._search_active:
            hint.update("")
            return
        recursive = "ON" if self._recursive else "OFF"
        pieces = [
            f"recursive {recursive} (r)",
            "Enter: open",
            "Esc: clear / close",
        ]
        if self._search_note:
            pieces.insert(1, self._search_note)
        hint.update(Text(" · ".join(pieces), style="#6f8076"))

    def _set_search_busy(self, busy: bool, note: str = "") -> None:
        self._search_busy = busy
        self._search_note = note
        self._update_search_hint()
        self._update_status()

    def _cancel_search_timer(self) -> None:
        if self._search_timer is not None:
            try:
                self._search_timer.stop()
            except Exception:
                pass
            self._search_timer = None

    def action_search(self) -> None:
        if self._search_active:
            self._search_input().focus()
            return
        if self._error:
            return
        selected = self._current_record()
        self._search_active = True
        self._search_query = ""
        self._search_note = ""
        self._search_token += 1
        box = self.query_one("#search-box", Vertical)
        box.add_class("active")
        field = self._search_input()
        field.value = ""
        self._set_display_records(
            self._all_records,
            select_path=selected.path if selected else None,
        )
        field.focus()
        self._update_search_hint()
        self._update_status()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search-input" or not self._search_active:
            return
        self._search_query = event.value
        self._search_token += 1
        self._cancel_search_timer()
        if self._recursive and self._search_query.strip():
            self._search_note = "searching…"
            self._set_search_busy(True, "searching…")
            token = self._search_token
            self._search_timer = self.set_timer(
                SEARCH_DEBOUNCE,
                lambda: self._start_recursive_search(token),
            )
            return

        self._recursive_results = None
        self._set_search_busy(False)
        results = linear_search(self._all_records, self._search_query)
        empty_message = (
            f"No files match “{self._search_query}”."
            if self._search_query.strip()
            else "This directory is empty."
        )
        self._set_display_records(results, empty_message=empty_message)

    def _start_recursive_search(self, token: int) -> None:
        self._search_timer = None
        if not self._search_active or not self._recursive or token != self._search_token:
            return
        query = self._search_query
        if not query.strip():
            return
        self._set_search_busy(True, "searching recursively…")
        self._recursive_search_worker(token, query, self.current_dir)

    @work(exclusive=True, group="search")
    async def _recursive_search_worker(
        self,
        token: int,
        query: str,
        root: Path,
    ) -> None:
        try:
            matches, walk = await asyncio.to_thread(
                self._collect_recursive,
                root,
                query,
            )
        except Exception as error:
            if token != self._search_token:
                return
            self._set_search_busy(False, f"search failed: {error}")
            self._set_display_records([], empty_message=f"Search failed: {error}")
            return
        if token != self._search_token or not self._search_active:
            return
        self._recursive_results = matches
        note_parts = []
        if walk.truncated:
            note_parts.append(f"limited to {config.MAX_RECURSIVE_RESULTS} entries")
        if walk.issues:
            note_parts.append(f"{len(walk.issues)} unreadable/inaccessible path(s) skipped")
        self._set_search_busy(False, "; ".join(note_parts))
        empty_message = (
            f"No files match “{query}”."
            if query.strip()
            else "This directory is empty."
        )
        self._set_display_records(matches, empty_message=empty_message)
        self._update_status()

    def _collect_recursive(self, root: Path, query: str) -> tuple[list[FileRecord], TraversalResult]:
        # Traversal filters names early so the result cap is spent on matches;
        # linear_search still performs the final documented comparison.
        walk = walk_directory(
            root,
            filename_filter=query,
            recursive=True,
            follow_symlinks=False,
            max_depth=config.MAX_RECURSIVE_DEPTH,
            max_results=config.MAX_RECURSIVE_RESULTS,
        )
        records: list[FileRecord] = []
        for path in walk.paths:
            try:
                records.append(FileRecord.from_path(path))
            except OSError:
                continue
        records = sort_records(records, self._sort_key, reverse=self._sort_reverse)
        return linear_search(records, query), walk

    def _deactivate_search(
        self,
        *,
        restore: bool = True,
        select_path: Path | str | None = None,
    ) -> None:
        self._cancel_search_timer()
        self._search_token += 1
        was_active = self._search_active
        self._search_active = False
        self._search_query = ""
        self._search_note = ""
        self._search_busy = False
        self._recursive_results = None
        try:
            self.query_one("#search-box", Vertical).remove_class("active")
            field = self._search_input()
            if field.value:
                field.value = ""
        except Exception:
            pass
        self._update_search_hint()
        if restore and was_active:
            self._set_display_records(self._all_records, select_path=select_path)
            try:
                self.query_one("#files", DataTable).focus()
            except Exception:
                pass
        self._update_status()

    def action_escape(self) -> None:
        if not self._search_active:
            return
        field = self._search_input()
        if field.value:
            field.value = ""
            return
        selected = self._current_record()
        self._deactivate_search(
            restore=True,
            select_path=selected.path if selected else None,
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self._open_selected()

    def action_toggle_recursive(self) -> None:
        self._recursive = not self._recursive
        if self._search_active:
            self._cancel_search_timer()
            self._search_token += 1
            self._update_search_hint()
            if self._recursive and self._search_query.strip():
                self._search_note = "searching…"
                self._set_search_busy(True, "searching…")
                token = self._search_token
                self._search_timer = self.set_timer(
                    SEARCH_DEBOUNCE,
                    lambda: self._start_recursive_search(token),
                )
            else:
                self._recursive_results = None
                self._set_search_busy(False)
                results = linear_search(self._all_records, self._search_query)
                empty_message = (
                    f"No files match “{self._search_query}”."
                    if self._search_query.strip()
                    else "This directory is empty."
                )
                self._set_display_records(results, empty_message=empty_message)
        self._update_status()

    # ------------------------------------------------------------------ actions
    def action_cursor_up(self) -> None:
        if not self._display_records:
            return
        table = self.query_one("#files", DataTable)
        table.move_cursor(row=max(0, self._selected_index - 1), animate=False)

    def action_cursor_down(self) -> None:
        if not self._display_records:
            return
        table = self.query_one("#files", DataTable)
        table.move_cursor(
            row=min(len(self._display_records) - 1, self._selected_index + 1),
            animate=False,
        )

    def action_open_selected(self) -> None:
        self._open_selected()

    def _open_selected(self) -> None:
        record = self._current_record()
        if record is None:
            if self._search_active:
                self.notify("No search result is selected.", severity="warning")
            return
        if record.is_dir:
            self._navigate(record.path)
        elif record.kind is FileKind.VIDEO:
            self._play_selected()
        else:
            self._start_preview(record, force=True)

    def action_preview_selected(self) -> None:
        record = self._current_record()
        if record is None:
            return
        self._start_preview(record, force=True)

    def action_play_selected(self) -> None:
        self._play_selected()

    def _play_selected(self) -> None:
        record = self._current_record()
        if record is None:
            return
        if record.kind is not FileKind.VIDEO:
            self.notify("mpv playback is available for video files only.", severity="warning")
            return
        if not player_available():
            self.notify("mpv not found; install mpv to play videos.", severity="error")
            self._start_preview(record, force=True)
            return
        try:
            with self.suspend():
                result = self._player(record.path)
        except Exception as error:
            result = PlaybackResult(False, f"Cannot run mpv: {error}")
        self.notify(
            result.message,
            title=config.APP_TITLE,
            severity="information" if result.ok else "error",
        )
        self._start_preview(record, force=True)
        self._update_status()

    def action_parent(self) -> None:
        parent = self.current_dir.parent
        if parent == self.current_dir:
            self.notify("Already at the filesystem root.", severity="warning")
            return
        self._navigate(parent)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_quit(self) -> None:
        self.exit()

    # -------------------------------------------------------------------- sort
    def _set_sort(self, key: str) -> None:
        if self._error:
            return
        self._sort_key = key
        self._resort()

    def _resort(self) -> None:
        selected = self._current_record()
        select_path = selected.path if selected else None
        self._all_records = sort_records(
            self._all_records,
            self._sort_key,
            reverse=self._sort_reverse,
        )
        if self._search_active:
            if self._recursive_results is not None or (
                self._recursive and self._search_query.strip()
            ):
                if self._recursive_results is not None:
                    self._recursive_results = sort_records(
                        self._recursive_results,
                        self._sort_key,
                        reverse=self._sort_reverse,
                    )
                    self._set_display_records(
                        self._recursive_results,
                        select_path=select_path,
                    )
            else:
                results = linear_search(self._all_records, self._search_query)
                self._set_display_records(results, select_path=select_path)
        else:
            self._set_display_records(self._all_records, select_path=select_path)
        self._update_status()

    def action_sort_name(self) -> None:
        self._set_sort("name")

    def action_sort_size(self) -> None:
        self._set_sort("size")

    def action_sort_type(self) -> None:
        self._set_sort("type")

    def action_sort_mtime(self) -> None:
        self._set_sort("mtime")

    def action_toggle_order(self) -> None:
        if self._error:
            return
        self._sort_reverse = not self._sort_reverse
        self._resort()

    # ------------------------------------------------------------------ status
    def _update_status(self) -> None:
        try:
            status = self.query_one("#statusbar", Static)
        except Exception:
            return
        if self._error:
            text = f"STATUS: ERROR — {self._error} | Backspace: parent | q: quit"
            status.update(Text(text, style="#ff9b90"))
            return

        mode = "NORMAL MODE"
        if self._search_active and self._recursive:
            mode = "RECURSIVE SEARCH"
        elif self._search_active:
            mode = "SEARCH"
        elif self._recursive:
            mode = "RECURSIVE"

        if self._search_active:
            count = len(self._display_records)
            noun = "result" if count == 1 else "results"
            parts = [f"STATUS: {count} {noun}"]
            if self._search_busy:
                parts.append("searching")
            query = self._search_query or "(empty)"
            parts.append(f"query: {query}")
        else:
            count = len(self._all_records)
            noun = "item" if count == 1 else "items"
            parts = [f"STATUS: {count} {noun}"]

        record = self._current_record()
        if record is not None:
            name = record.name
            if self._search_active and record.path.parent != self.current_dir:
                try:
                    name = str(record.path.relative_to(self.current_dir))
                except ValueError:
                    pass
            parts.append(name)
        parts.append(mode)
        parts.append(
            f"sort: {self._sort_key} {'desc' if self._sort_reverse else 'asc'}"
        )
        if not self._preview_visible:
            parts.append("preview hidden (narrow terminal)")
        status.update(Text(" | ".join(parts), style="#9fb0a5"))

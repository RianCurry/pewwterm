"""Integration tests for the Textual application.

A fake preview builder keeps these tests deterministic and independent of
FFmpeg/Poppler/Chafa.  The real text preview path is exercised in one test, and
external subprocess integration is covered in ``test_integration.py``.
"""

from __future__ import annotations

import time
from contextlib import nullcontext
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Static

from pewwterm.app import MIN_PREVIEW_WIDTH, HelpScreen, PewwTermApp
from pewwterm.models import FileKind
from pewwterm.player import PlaybackResult
from pewwterm.preview import PreviewResult, build_preview


def fake_preview(record, width, height):
    return PreviewResult(
        kind=record.kind.value,
        title=record.name,
        metadata=[f"Fake type: {record.type_label}"],
        body=f"Preview body for {record.name}",
        record=record,
    )


def text_of(widget: Static) -> str:
    return str(widget.content)


def test_every_advertised_app_binding_has_an_action() -> None:
    app = PewwTermApp(".")
    for binding in PewwTermApp.BINDINGS:
        assert callable(getattr(app, f"action_{binding.action}"))


async def test_app_starts_and_displays_real_directory(
    media_tree: Path,
) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.35)
        table = app.query_one("#files", DataTable)
        assert app.current_dir == media_tree.resolve()
        assert table.row_count == 9
        assert len(app._display_records) == 9
        assert app._last_preview is not None
        assert app._last_preview.title == app._current_record().name
        assert "STATUS:" in text_of(app.query_one("#statusbar", Static))
        assert "NORMAL MODE" in text_of(app.query_one("#statusbar", Static))
        assert str(media_tree.resolve()) in text_of(app.query_one("#location", Static))


async def test_keyboard_navigation_updates_selection_and_preview(
    media_tree: Path,
) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        assert app._selected_index == 0
        await pilot.press("down")
        await pilot.pause(0.2)
        assert app._selected_index == 1
        assert app._last_preview.title == app._current_record().name
        await pilot.press("up")
        await pilot.pause(0.2)
        assert app._selected_index == 0
        await pilot.press("down", "down", "down")
        await pilot.pause(0.2)
        assert app._selected_index == 3


async def test_enter_opens_directory_and_backspace_returns(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        project_index = next(
            index
            for index, record in enumerate(app._display_records)
            if record.name == "project"
        )
        app.query_one("#files", DataTable).move_cursor(row=project_index)
        await pilot.pause(0.15)
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app.current_dir.name == "project"
        assert {record.name for record in app._display_records} == {"main.py", "deep"}

        await pilot.press("backspace")
        await pilot.pause(0.2)
        assert app.current_dir == media_tree.resolve()


async def test_search_filters_selects_and_clears(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("slash")
        assert app._search_active is True
        assert app.query_one("#search-input", Input).has_focus
        await pilot.press("t", "x", "t")
        await pilot.pause(0.2)
        names = {record.name for record in app._display_records}
        assert names == {"alpha.txt", "space file.txt", "catatan ä.txt"}
        first_preview = app._last_preview.title

        await pilot.press("down")
        await pilot.pause(0.2)
        assert app._selected_index == 1
        selected = app._current_record()
        await pilot.press("enter")
        await pilot.pause(0.25)
        assert app._last_preview.title == selected.name
        assert app._last_preview.title != first_preview or selected.name == first_preview

        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app._search_active is True
        assert app.query_one("#search-input", Input).value == ""
        assert len(app._display_records) == len(app._all_records)

        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app._search_active is False
        assert not app.query_one("#search-box").has_class("active")
        assert app.query_one("#files", DataTable).has_focus


async def test_search_empty_state(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("slash")
        await pilot.press("z", "z", "z", "z")
        await pilot.pause(0.2)
        assert app._display_records == []
        empty = app.query_one("#empty-state", Static)
        assert empty.display is True
        assert "No files match" in text_of(empty)
        assert app._last_preview.kind == "empty"
        await pilot.press("enter")
        await pilot.pause(0.1)
        await pilot.press("escape", "escape")
        await pilot.pause(0.1)
        assert app._search_active is False


async def test_recursive_search_finds_nested_file(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("r")
        assert app._recursive is True
        await pilot.press("slash")
        await pilot.press("t", "a", "r", "g", "e", "t")
        await pilot.pause(0.7)
        assert [record.name for record in app._display_records] == ["target.txt"]
        assert app._display_records[0].path.parent.name == "deep"
        assert "RECURSIVE SEARCH" in text_of(app.query_one("#statusbar", Static))
        hint = text_of(app.query_one("#search-hint", Static))
        assert "recursive ON" in hint
        await pilot.press("enter")
        await pilot.pause(0.25)
        assert app._last_preview.title == "target.txt"
        await pilot.press("escape", "escape")
        await pilot.pause(0.1)
        assert app._search_active is False
        assert app._recursive is True


async def test_ctrl_r_toggles_recursive_while_typing(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("slash")
        await pilot.press("t", "a", "r", "g", "e", "t")
        await pilot.pause(0.2)
        assert app._recursive is False
        assert app._display_records == []
        await pilot.press("ctrl+r")
        await pilot.pause(0.7)
        assert app._recursive is True
        assert app.query_one("#search-input", Input).value == "target"
        assert [record.name for record in app._display_records] == ["target.txt"]
        assert "RECURSIVE SEARCH" in text_of(app.query_one("#statusbar", Static))

        await pilot.press("ctrl+r")
        await pilot.pause(0.5)
        assert app._recursive is False
        assert app._display_records == []
        assert "SEARCH" in text_of(app.query_one("#statusbar", Static))

        await pilot.press("escape", "escape")
        await pilot.pause(0.1)
        assert app._search_active is False


async def test_help_screen_opens_and_closes(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("question_mark")
        await pilot.pause(0.2)
        assert isinstance(app.screen, HelpScreen)
        body = text_of(app.screen.query_one("#help-body", Static))
        assert "KEYBOARD HELP" in body
        assert "Backspace" in body
        assert "chafa" in body
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, HelpScreen)


async def test_sorting_and_order_toggle(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("2")
        await pilot.pause(0.1)
        assert app._sort_key == "size"
        sizes = [record.size if record.size is not None else -1 for record in app._display_records]
        assert sizes == sorted(sizes)
        first = app._display_records[0].name

        await pilot.press("o")
        await pilot.pause(0.1)
        assert app._sort_reverse is True
        assert app._display_records[-1].name == first
        sizes_desc = [record.size if record.size is not None else -1 for record in app._display_records]
        assert sizes_desc == sorted(sizes_desc, reverse=True)

        await pilot.press("3")
        await pilot.pause(0.1)
        assert app._sort_key == "type"
        await pilot.press("4")
        await pilot.pause(0.1)
        assert app._sort_key == "mtime"
        await pilot.press("1")
        await pilot.pause(0.1)
        assert app._sort_key == "name"
        assert "sort: name desc" in text_of(app.query_one("#statusbar", Static))


async def test_space_refreshes_preview(media_tree: Path) -> None:
    calls = {"count": 0}

    def counting_preview(record, width, height):
        calls["count"] += 1
        return fake_preview(record, width, height)

    app = PewwTermApp(media_tree, preview_builder=counting_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        before = calls["count"]
        await pilot.press("space")
        await pilot.pause(0.25)
        assert calls["count"] > before


async def test_long_preview_does_not_block_loading_state(media_tree: Path) -> None:
    def slow_preview(record, width, height):
        time.sleep(0.4)
        return fake_preview(record, width, height)

    app = PewwTermApp(media_tree, preview_builder=slow_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.05)
        await pilot.press("down")
        await pilot.pause(0.05)
        assert "Loading preview" in text_of(app.query_one("#preview-content", Static))
        await pilot.pause(0.6)
        assert app._last_preview.title == app._current_record().name


async def test_error_state_for_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing-directory"
    app = PewwTermApp(missing, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)
        assert app._error and "not found" in app._error.lower()
        assert "ERROR" in text_of(app.query_one("#statusbar", Static))
        empty = app.query_one("#empty-state", Static)
        assert empty.display is True
        assert "not found" in text_of(empty).lower()
        assert app._last_preview.kind == "error"
        assert app.query_one("#files", DataTable).display is False


async def test_empty_directory_state(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    app = PewwTermApp(empty_dir, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)
        assert app._error is None
        assert app._display_records == []
        assert app.query_one("#empty-state", Static).display is True
        assert "empty" in text_of(app.query_one("#empty-state", Static)).lower()
        assert app._last_preview.kind == "empty"


async def test_responsive_layout_hides_and_restores_preview(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        assert app._preview_visible is True
        await pilot.resize_terminal(80, 24)
        await pilot.pause(0.2)
        assert MIN_PREVIEW_WIDTH > 80
        assert app._preview_visible is False
        assert app.query_one("#preview-panel").display is False
        assert app.query_one("#files-panel").has_class("full")
        assert "preview hidden" in text_of(app.query_one("#statusbar", Static))

        await pilot.resize_terminal(120, 40)
        await pilot.pause(0.3)
        assert app._preview_visible is True
        assert app.query_one("#preview-panel").display is True
        assert not app.query_one("#files-panel").has_class("full")
        assert app._last_preview is not None


async def test_real_text_preview_is_integrated(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("actual preview text\n", encoding="utf-8")
    app = PewwTermApp(tmp_path, preview_builder=build_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        assert app._last_preview is not None
        assert app._last_preview.kind == "text"
        assert "actual preview text" in app._last_preview.body


async def test_video_record_is_dispatched_for_playback(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        video_index = next(
            index
            for index, record in enumerate(app._display_records)
            if record.kind is FileKind.VIDEO
        )
        app.query_one("#files", DataTable).move_cursor(row=video_index)
        await pilot.pause(0.15)
        assert app._current_record().kind is FileKind.VIDEO
        # Do not press Enter here: MPV/suspend is exercised by player unit tests.
        assert app._last_preview.title == app._current_record().name


async def test_play_shortcut_dispatches_video_to_player(
    media_tree: Path, monkeypatch
) -> None:
    calls: list[Path] = []

    def fake_player(path: Path) -> PlaybackResult:
        calls.append(path)
        return PlaybackResult(True, "fake mpv exited")

    app = PewwTermApp(media_tree, preview_builder=fake_preview, player=fake_player)
    monkeypatch.setattr(PewwTermApp, "suspend", lambda self: nullcontext())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        video_index = next(
            index
            for index, record in enumerate(app._display_records)
            if record.kind is FileKind.VIDEO
        )
        app.query_one("#files", DataTable).move_cursor(row=video_index)
        await pilot.pause(0.15)
        await pilot.press("p")
        await pilot.pause(0.3)
        assert calls == [app._current_record().path]


async def test_initial_file_is_selected(media_tree: Path) -> None:
    video = media_tree / "clip.mp4"
    app = PewwTermApp(media_tree, initial_file=video, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        assert app.current_dir == media_tree.resolve()
        assert app._current_record() is not None
        assert app._current_record().name == "clip.mp4"
        assert app._last_preview.title == "clip.mp4"


async def test_relative_initial_file_is_selected(
    media_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(media_tree)
    app = PewwTermApp(".", initial_file="clip.mp4", preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        assert app.current_dir == media_tree.resolve()
        assert app._current_record() is not None
        assert app._current_record().name == "clip.mp4"


async def test_relative_file_argument_opens_parent_and_selects(
    media_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(media_tree)
    app = PewwTermApp("clip.mp4", preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        assert app.current_dir == media_tree.resolve()
        assert app._current_record() is not None
        assert app._current_record().name == "clip.mp4"


async def test_opening_search_preserves_the_current_selection(media_tree: Path) -> None:
    app = PewwTermApp(media_tree, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        app.query_one("#files", DataTable).move_cursor(row=3)
        await pilot.pause(0.2)
        selected = app._current_record().name

        await pilot.press("slash")
        await pilot.pause(0.2)
        assert app._current_record().name == selected

        await pilot.press("escape", "escape")
        await pilot.pause(0.2)
        assert app._search_active is False
        assert app._current_record().name == selected


async def test_sorting_does_not_mask_an_error_state(tmp_path: Path) -> None:
    missing = tmp_path / "missing-directory"
    app = PewwTermApp(missing, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)
        assert app._last_preview.kind == "error"

        await pilot.press("2")
        await pilot.pause(0.2)
        assert app._last_preview.kind == "error"
        assert "not found" in text_of(app.query_one("#empty-state", Static)).lower()

        await pilot.press("o")
        await pilot.pause(0.2)
        assert app._last_preview.kind == "error"


async def test_search_does_not_mask_an_error_state(tmp_path: Path) -> None:
    missing = tmp_path / "missing-directory"
    app = PewwTermApp(missing, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)
        await pilot.press("slash")
        await pilot.pause(0.2)
        assert app._search_active is False
        assert app._last_preview.kind == "error"
        assert "not found" in text_of(app.query_one("#empty-state", Static)).lower()


async def test_enter_symlinked_directory_is_reversible(
    tmp_path: Path, no_symlink_support: bool
) -> None:
    if no_symlink_support:
        pytest.skip("filesystem does not support symlinks")
    root = tmp_path / "links"
    target = tmp_path / "target"
    root.mkdir()
    target.mkdir()
    (target / "inside.txt").write_text("inside", encoding="utf-8")
    (root / "shortcut").symlink_to(target, target_is_directory=True)

    app = PewwTermApp(root, preview_builder=fake_preview)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        app.query_one("#files", DataTable).move_cursor(row=0)
        await pilot.pause(0.15)
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app.current_dir == root.resolve() / "shortcut"
        assert [record.name for record in app._display_records] == ["inside.txt"]

        await pilot.press("backspace")
        await pilot.pause(0.2)
        assert app.current_dir == root.resolve()

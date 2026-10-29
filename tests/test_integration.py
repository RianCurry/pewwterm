"""Cross-module integration tests with temporary files and mocked subprocesses."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pewwterm import __main__ as cli
from pewwterm import config
from pewwterm.models import FileKind, FileRecord, build_file_records, sort_records
from pewwterm.player import play_video
from pewwterm.preview import build_preview
from pewwterm.search import linear_search
from pewwterm.traversal import walk_directory


def test_discovery_filter_search_and_preview_pipeline(media_tree: Path) -> None:
    records = sort_records(build_file_records(media_tree), "name")
    matches = linear_search(records, "alpha")
    assert len(matches) == 1
    result = build_preview(matches[0])
    assert result.kind == "text"
    assert "hello alpha" in result.body

    walk = walk_directory(media_tree, filename_filter="target", recursive=True)
    assert [path.name for path in walk.paths] == ["target.txt"]
    nested_record = FileRecord.from_path(walk.paths[0])
    nested_preview = build_preview(nested_record)
    assert nested_preview.kind == "text"
    assert "needle" in nested_preview.body


def test_video_preview_and_mpv_invocation_share_record(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "demo clip.mp4"
    video.write_bytes(b"pretend video bytes")
    fake_tools(
        {
            "ffprobe": "/fake/ffprobe",
            "ffmpeg": "/fake/ffmpeg",
            "chafa": None,
            "mpv": "/fake/mpv",
        }
    )
    probe_payload = {
        "format": {"duration": "3.5", "format_name": "matroska,webm"},
        "streams": [
            {"codec_type": "video", "codec_name": "vp9", "width": 1280, "height": 720}
        ],
    }
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        assert "shell" not in kwargs
        if "ffprobe" in command[0]:
            return subprocess.CompletedProcess(command, 0, json.dumps(probe_payload), "")
        if "ffmpeg" in command[0]:
            Image.new("RGB", (64, 36), (1, 2, 3)).save(Path(command[-1]), format="JPEG")
            return subprocess.CompletedProcess(command, 0, "", "")
        if "mpv" in command[0]:
            return subprocess.CompletedProcess(command, 0)
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("subprocess.run", fake_run)
    record = FileRecord.from_path(video)
    assert record.kind is FileKind.VIDEO
    preview = build_preview(record, width=24, height=8)
    assert preview.kind == "video"
    assert preview.art
    assert any("1280 x 720" in line for line in preview.metadata)
    assert any("0:04" in line for line in preview.metadata)

    playback = play_video(record.path)
    assert playback.ok is True
    mpv_commands = [command for command in commands if "mpv" in command[0]]
    assert len(mpv_commands) == 1
    assert str(video) in mpv_commands[0]


def test_missing_tools_do_not_crash_preview_pipeline(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "x.mp4"
    video.write_bytes(b"x")
    fake_tools({})

    def should_not_run(command, **kwargs):  # pragma: no cover - failure path helper
        raise AssertionError("subprocess must not run when tools are missing")

    monkeypatch.setattr("subprocess.run", should_not_run)
    result = build_preview(FileRecord.from_path(video))
    assert result.kind == "video"
    assert result.error is not None
    assert result.notice is not None
    assert "ffprobe" in result.error
    assert "ffmpeg" in result.notice


def test_cli_check_reports_dependencies(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--check"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "python" in output
    assert "mpv" in output
    assert "cache" in output


def test_cli_parser_accepts_file_and_directory(media_tree: Path) -> None:
    parser = cli.build_parser()
    args = parser.parse_args([str(media_tree)])
    assert Path(args.directory) == media_tree
    args = parser.parse_args([])
    assert args.directory == "."


def test_cli_file_argument_opens_parent_and_selects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"pretend")
    captured: dict[str, object] = {}

    class FakeApp:
        def __init__(self, start, *, initial_file=None):
            captured["start"] = start
            captured["initial_file"] = initial_file

        def run(self) -> None:
            captured["ran"] = True

    monkeypatch.setattr("pewwterm.app.PewwTermApp", FakeApp)
    assert cli.main([str(video)]) == 0
    assert captured["start"] == video.parent
    assert captured["initial_file"] == video
    assert captured["ran"] is True


def test_cli_keyboard_interrupt_exits_with_130(monkeypatch: pytest.MonkeyPatch) -> None:
    class InterruptedApp:
        def __init__(self, start, *, initial_file=None):
            self.start = start

        def run(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("pewwterm.app.PewwTermApp", InterruptedApp)
    assert cli.main([]) == 130


def test_cli_symlinked_file_preserves_link_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_symlink_support: bool,
) -> None:
    if no_symlink_support:
        pytest.skip("filesystem does not support symlinks")
    target_directory = tmp_path / "real"
    target_directory.mkdir()
    target = target_directory / "clip.mp4"
    target.write_bytes(b"x")
    link = tmp_path / "linked.mp4"
    link.symlink_to(target)
    captured: dict[str, object] = {}

    class FakeApp:
        def __init__(self, start, *, initial_file=None):
            captured["start"] = start
            captured["initial_file"] = initial_file

        def run(self) -> None:
            captured["ran"] = True

    monkeypatch.setattr("pewwterm.app.PewwTermApp", FakeApp)
    assert cli.main([str(link)]) == 0
    assert captured["start"] == link.parent
    assert captured["initial_file"] == link
    assert captured["ran"] is True


def test_cache_dir_falls_back_when_default_home_is_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PEWWTERM_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    blocked_home = tmp_path / "home-is-a-file"
    blocked_home.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: blocked_home))
    monkeypatch.setattr(config.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))

    result = config.cache_dir()

    assert result == tmp_path / "tmp" / config.APP_NAME
    assert result.is_dir()

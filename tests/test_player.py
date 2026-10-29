"""Tests for MPV discovery and safe subprocess invocation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pewwterm import player


def test_missing_mpv_returns_helpful_message(tmp_path: Path, fake_tools) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    fake_tools({"mpv": None})
    result = player.play_video(video)
    assert result.ok is False
    assert "mpv not found" in result.message


def test_missing_file_is_rejected(tmp_path: Path, fake_tools) -> None:
    fake_tools({"mpv": "/fake/mpv"})
    result = player.play_video(tmp_path / "missing.mp4")
    assert result.ok is False
    assert "not found" in result.message.lower()


def test_directory_is_rejected(tmp_path: Path, fake_tools) -> None:
    fake_tools({"mpv": "/fake/mpv"})
    result = player.play_video(tmp_path)
    assert result.ok is False
    assert "regular video" in result.message


def test_success_uses_argument_list(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "clip with space.mp4"
    video.write_bytes(b"x")
    fake_tools({"mpv": "/fake/mpv"})
    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(command)
        assert kwargs.get("check") is False
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)
    result = player.play_video(video, extra_args=["--fs"])
    assert result.ok is True
    assert result.returncode == 0
    assert captured == [
        [
            "/fake/mpv",
            "--really-quiet",
            "--force-window=yes",
            "--no-terminal",
            "--fs",
            str(video),
        ]
    ]


def test_nonzero_exit_is_reported(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    fake_tools({"mpv": "/fake/mpv"})
    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 7),
    )
    result = player.play_video(video)
    assert result.ok is False
    assert result.returncode == 7
    assert "code 7" in result.message


def test_start_failure_is_reported(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    fake_tools({"mpv": "/fake/mpv"})

    def explode(command, **kwargs):
        raise OSError("no display")

    monkeypatch.setattr("subprocess.run", explode)
    result = player.play_video(video)
    assert result.ok is False
    assert "Cannot start mpv" in result.message


def test_player_available(fake_tools) -> None:
    fake_tools({"mpv": "/fake/mpv"})
    assert player.player_available() is True
    fake_tools({"mpv": None})
    assert player.player_available() is False

"""Tests for preview dispatch, image fallback, video and document backends."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pewwterm import document_preview, image_preview, video_preview
from pewwterm.models import FileRecord
from pewwterm.preview import build_preview, empty_preview, error_preview


def make_png(path: Path, size: tuple[int, int] = (64, 32)) -> None:
    Image.new("RGB", size, (20, 120, 70)).save(path)


def record(path: Path) -> FileRecord:
    return FileRecord.from_path(path)


def test_directory_preview(media_tree: Path) -> None:
    result = build_preview(record(media_tree))
    assert result.kind == "directory"
    assert result.metadata[0] == "Filename: Media"
    assert any("2 directories, 7 files" in line for line in result.metadata)
    assert "Enter" in result.actions[0]


def test_text_markdown_and_code_previews(tmp_path: Path) -> None:
    text = tmp_path / "note.txt"
    text.write_text("plain text\nsecond line", encoding="utf-8")
    markdown = tmp_path / "readme.md"
    markdown.write_text("# Heading\n\nBody", encoding="utf-8")
    code = tmp_path / "main.py"
    code.write_text("print('hello')", encoding="utf-8")

    text_result = build_preview(record(text))
    assert text_result.kind == "text"
    assert "plain text" in text_result.body
    assert text_result.body_format == "text"

    markdown_result = build_preview(record(markdown))
    assert markdown_result.kind == "markdown"
    assert markdown_result.body_format == "markdown"
    assert "# Heading" in markdown_result.body

    code_result = build_preview(record(code))
    assert code_result.kind == "code"
    assert "print" in code_result.body


def test_text_preview_limits_large_file(tmp_path: Path) -> None:
    big = tmp_path / "big.log"
    big.write_text("\n".join(f"line {index}" for index in range(50)), encoding="utf-8")
    document = document_preview.read_text_document(big, max_bytes=40, max_lines=2)
    assert document.truncated is True
    assert len(document.text.splitlines()) == 2
    assert document.notice and "truncated" in document.notice.lower()


def test_binary_text_preview_is_rejected(tmp_path: Path) -> None:
    binary = tmp_path / "data.bin"
    binary.write_bytes(b"abc\x00def")
    result = build_preview(record(binary))
    assert result.kind == "other"

    fake_text = tmp_path / "fake.txt"
    fake_text.write_bytes(b"abc\x00def")
    text_result = build_preview(record(fake_text))
    assert text_result.error is not None
    assert "binary" in text_result.error.lower()


def test_unsupported_preview(tmp_path: Path) -> None:
    blob = tmp_path / "file.xyz"
    blob.write_bytes(b"1234")
    result = build_preview(record(blob))
    assert result.kind == "other"
    assert "No built-in preview" in result.body
    assert result.actions == ["No default action"]


def test_image_preview_uses_pillow_fallback_when_chafa_missing(
    tmp_path: Path, fake_tools
) -> None:
    picture = tmp_path / "picture.png"
    make_png(picture)
    fake_tools({"chafa": None})
    result = build_preview(record(picture), width=32, height=12)
    assert result.kind == "image"
    assert result.error is None
    assert result.art
    assert result.art_format == "text"
    assert any("64 x 32" in line for line in result.metadata)
    assert any("ASCII fallback" in line for line in result.metadata)
    assert result.notice and "chafa not found" in result.notice


def test_image_preview_uses_chafa_arguments(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    picture = tmp_path / "picture.png"
    make_png(picture)
    fake_tools({"chafa": "/fake/chafa"})
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs.get("check") is False
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(command, 0, "\x1b[32m██\x1b[0m", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = image_preview.render_image(picture, columns=20, rows=8)
    assert result.backend == "chafa"
    assert "██" in result.text
    assert calls
    assert "--format" in calls[0]
    assert "symbols" in calls[0]
    assert calls[0][calls[0].index("--probe") + 1] == "off"


def test_chafa_failure_falls_back_to_pillow(tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch) -> None:
    picture = tmp_path / "picture.png"
    make_png(picture)
    fake_tools({"chafa": "/fake/chafa"})

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "chafa exploded")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = image_preview.render_image(picture, columns=20, rows=8)
    assert result.backend == "pillow-ascii"
    assert result.text
    assert result.notice and "chafa could not render" in result.notice


def test_corrupt_image_is_graceful(tmp_path: Path, fake_tools) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"this is not an image")
    fake_tools({"chafa": None})
    result = build_preview(record(broken), width=20, height=8)
    assert result.kind == "image"
    assert result.error is not None
    assert result.art == ""
    assert result.notice


def test_video_preview_metadata_and_thumbnail(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"pretend video")
    fake_tools(
        {
            "ffprobe": "/fake/ffprobe",
            "ffmpeg": "/fake/ffmpeg",
            "chafa": None,
            "mpv": None,
        }
    )
    payload = {
        "format": {
            "duration": "65.0",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "bit_rate": "1200000",
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
            }
        ],
    }

    def fake_run(command, **kwargs):
        assert "shell" not in kwargs
        if "ffprobe" in command[0]:
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        output = Path(command[-1])
        make_png(output, (80, 45))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = build_preview(record(video), width=32, height=10)
    assert result.kind == "video"
    assert any("1:05" in line for line in result.metadata)
    assert any("1920 x 1080" in line for line in result.metadata)
    assert any("h264" in line for line in result.metadata)
    assert any("still frame" in line for line in result.metadata)
    assert result.art
    assert result.error is None
    assert result.notice and "mpv is not installed" in result.notice
    assert any("Install mpv" in action for action in result.actions)


def test_video_preview_handles_subprocess_failure(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "bad.mp4"
    video.write_bytes(b"bad")
    fake_tools({"ffprobe": "/fake/ffprobe", "ffmpeg": "/fake/ffmpeg", "mpv": None})

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "decoder exploded")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = build_preview(record(video))
    assert result.kind == "video"
    assert result.error is not None
    assert "ffprobe failed" in result.error
    assert result.notice and "Cannot create video thumbnail" in result.notice


def test_video_preview_missing_dependencies(tmp_path: Path, fake_tools) -> None:
    video = tmp_path / "missing-tools.mp4"
    video.write_bytes(b"x")
    fake_tools({})
    result = build_preview(record(video))
    assert any("ffprobe not found" in line for line in [result.error or ""])
    assert result.notice and "ffmpeg not found" in result.notice
    assert result.notice and "mpv is not installed" in result.notice


def test_probe_video_invalid_json(tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / "x.mp4"
    video.write_bytes(b"x")
    fake_tools({"ffprobe": "/fake/ffprobe"})
    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "not json", ""),
    )
    probe = video_preview.probe_video(video)
    assert probe.error and "invalid JSON" in probe.error


def test_pdf_text_preview_with_missing_thumbnail_tool(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    fake_tools({"pdftotext": "/fake/pdftotext", "pdftoppm": None, "chafa": None})
    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, "Hello PDF\n\fSecond page\n", ""
        ),
    )
    result = build_preview(record(pdf))
    assert result.kind == "pdf"
    assert "Hello PDF" in result.body
    assert "Second page" in result.body
    assert result.art == ""
    assert result.notice and "pdftoppm not found" in result.notice


def test_pdf_preview_with_page_thumbnail(
    tmp_path: Path, fake_tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    fake_tools(
        {
            "pdftotext": "/fake/pdftotext",
            "pdftoppm": "/fake/pdftoppm",
            "chafa": None,
        }
    )

    def fake_run(command, **kwargs):
        if "pdftotext" in command[0]:
            return subprocess.CompletedProcess(command, 0, "PDF body", "")
        prefix = Path(command[-1])
        make_png(Path(f"{prefix}.png"), (90, 120))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = build_preview(record(pdf), width=24, height=10)
    assert result.kind == "pdf"
    assert "PDF body" in result.body
    assert result.art
    assert any("first page" in line for line in result.metadata)


def test_pdf_preview_missing_poppler(tmp_path: Path, fake_tools) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    fake_tools({})
    result = build_preview(record(pdf))
    assert result.error is not None
    assert "pdftotext not found" in result.error


def test_empty_and_error_preview_builders() -> None:
    empty = empty_preview("Nothing here")
    assert empty.kind == "empty"
    assert "Nothing here" in empty.body
    error = error_preview("Cannot open", "Permission denied")
    assert error.is_error
    assert error.kind == "error"


def test_build_preview_kind_dispatch(tmp_path: Path, fake_tools) -> None:
    # An image suffix is classified as image even when the file is corrupt; the
    # backend reports the decoder failure instead of changing the kind.
    bad = tmp_path / "x.png"
    bad.write_bytes(b"bad")
    fake_tools({"chafa": None})
    assert build_preview(record(bad)).kind == "image"

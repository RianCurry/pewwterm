"""Shared pytest fixtures.

The cache override is autouse so no test writes thumbnails into the developer's
real ``~/.cache/pewwterm`` directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache = tmp_path / "cache"
    monkeypatch.setenv("PEWWTERM_CACHE_DIR", str(cache))
    return cache


@pytest.fixture
def media_tree(tmp_path: Path) -> Path:
    root = tmp_path / "Media"
    root.mkdir()
    (root / "alpha.txt").write_text("hello alpha\n", encoding="utf-8")
    (root / "Beta.md").write_text("# Beta\n\nmarkdown body\n", encoding="utf-8")
    (root / "space file.txt").write_text("spaces\n", encoding="utf-8")
    (root / "catatan ä.txt").write_text("unicode\n", encoding="utf-8")
    (root / "photo.png").write_bytes(b"not really a png yet")
    (root / "clip.mp4").write_bytes(b"not really a video")
    (root / "archive.bin").write_bytes(b"\x00\x01\x02")
    sub = root / "project"
    sub.mkdir()
    (sub / "main.py").write_text("print('hi')\n", encoding="utf-8")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "target.txt").write_text("needle\n", encoding="utf-8")
    empty = root / "empty dir"
    empty.mkdir()
    return root


@pytest.fixture
def fake_tools(monkeypatch: pytest.MonkeyPatch):
    """Return a helper that installs a config.which replacement."""

    from pewwterm import config

    def install(mapping: dict[str, str | None]) -> None:
        monkeypatch.setattr(config, "which", lambda tool: mapping.get(tool))

    return install


@pytest.fixture
def no_symlink_support(tmp_path: Path) -> bool:
    probe = tmp_path / "symlink-probe"
    try:
        os.symlink(tmp_path, probe)
        probe.unlink()
        return False
    except (OSError, NotImplementedError):
        return True

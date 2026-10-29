"""Tests for recursive traversal, filters, limits and symlink loops."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pewwterm.traversal import walk_directory


def names(result) -> list[str]:
    return [path.name for path in result.paths]


def test_recursive_walk_finds_nested_entries(media_tree: Path) -> None:
    result = walk_directory(media_tree, recursive=True)
    found = names(result)
    assert "alpha.txt" in found
    assert "main.py" in found
    assert "target.txt" in found
    assert "project" in found
    assert "deep" in found
    assert result.issues == []
    assert result.truncated is False


def test_non_recursive_walk_stops_at_root(media_tree: Path) -> None:
    result = walk_directory(media_tree, recursive=False)
    found = names(result)
    assert "alpha.txt" in found
    assert "project" in found
    assert "target.txt" not in found
    assert "main.py" not in found


def test_filename_filter_is_case_insensitive_and_partial(media_tree: Path) -> None:
    result = walk_directory(media_tree, filename_filter="TARGET")
    assert names(result) == ["target.txt"]


def test_extension_filter_accepts_optional_dot(media_tree: Path) -> None:
    result = walk_directory(media_tree, extensions=["TXT", ".md"])
    found = sorted(names(result))
    assert found == ["Beta.md", "alpha.txt", "catatan ä.txt", "space file.txt", "target.txt"]
    assert "project" not in found


def test_depth_limit(media_tree: Path) -> None:
    shallow = walk_directory(media_tree, max_depth=1)
    assert "main.py" in names(shallow)
    assert "target.txt" not in names(shallow)
    deeper = walk_directory(media_tree, max_depth=2)
    assert "target.txt" in names(deeper)


def test_result_limit_sets_truncated(media_tree: Path) -> None:
    result = walk_directory(media_tree, max_results=2)
    assert len(result.paths) == 2
    assert result.truncated is True


def test_invalid_root_paths(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        walk_directory(tmp_path / "missing")
    with pytest.raises(NotADirectoryError):
        walk_directory(file_path)
    with pytest.raises(ValueError):
        walk_directory(tmp_path, max_depth=-1)


def test_symlink_loop_terminates_when_following(tmp_path: Path, no_symlink_support: bool) -> None:
    if no_symlink_support:
        pytest.skip("filesystem does not support symlinks")
    root = tmp_path / "loop-root"
    child = root / "child"
    child.mkdir(parents=True)
    (child / "leaf.txt").write_text("leaf", encoding="utf-8")
    (child / "back").symlink_to(root, target_is_directory=True)

    result = walk_directory(root, follow_symlinks=True, max_results=100)
    assert "leaf.txt" in names(result)
    assert "back" in names(result)
    assert any("already visited" in issue.message for issue in result.issues)
    assert len(result.paths) < 20


def test_symlink_directories_are_not_followed_by_default(
    tmp_path: Path, no_symlink_support: bool
) -> None:
    if no_symlink_support:
        pytest.skip("filesystem does not support symlinks")
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    result = walk_directory(root)
    assert "link" in names(result)
    assert "secret.txt" not in names(result)


def test_permission_denied_subdirectory_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read mode-000 directories")
    root = tmp_path / "root"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "ok.txt").write_text("ok", encoding="utf-8")
    (blocked / "hidden.txt").write_text("hidden", encoding="utf-8")
    blocked.chmod(0o000)
    try:
        result = walk_directory(root)
    finally:
        blocked.chmod(0o755)
    assert "ok.txt" in names(result)
    assert any(issue.path.name == "blocked" for issue in result.issues)
    assert "hidden.txt" not in names(result)


def test_deterministic_validated_order(tmp_path: Path) -> None:
    root = tmp_path / "ordered"
    root.mkdir()
    for name in ("b.txt", "A.txt", "c.txt"):
        (root / name).write_text(name, encoding="utf-8")
    result = walk_directory(root)
    assert names(result) == ["A.txt", "b.txt", "c.txt"]

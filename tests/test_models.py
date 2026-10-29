"""Tests for file classification, records, list helpers and sorting."""

from __future__ import annotations

from pathlib import Path

import pytest

from pewwterm.models import (
    FileKind,
    FileRecord,
    build_file_records,
    classify_path,
    format_mtime,
    human_size,
    index_of_path,
    insert_record,
    kind_from_suffix,
    remove_record,
    sort_records,
)


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".PNG", FileKind.IMAGE),
        (".jpeg", FileKind.IMAGE),
        (".webp", FileKind.IMAGE),
        (".mp4", FileKind.VIDEO),
        (".MKV", FileKind.VIDEO),
        (".pdf", FileKind.PDF),
        (".md", FileKind.MARKDOWN),
        (".txt", FileKind.TEXT),
        (".py", FileKind.CODE),
        (".json", FileKind.CODE),
        (".xyz", FileKind.OTHER),
        ("", FileKind.OTHER),
    ],
)
def test_kind_from_suffix(suffix: str, expected: FileKind) -> None:
    assert kind_from_suffix(suffix) is expected


def test_classify_path_directory_file_and_missing(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    text = tmp_path / "note.txt"
    text.write_text("x", encoding="utf-8")
    assert classify_path(folder) is FileKind.DIRECTORY
    assert classify_path(text) is FileKind.TEXT
    with pytest.raises(FileNotFoundError):
        classify_path(tmp_path / "missing")


def test_human_size_and_mtime_formatting() -> None:
    assert human_size(None) == "-"
    assert human_size(-1) == "-"
    assert human_size(0) == "0 B"
    assert human_size(1023) == "1023 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(1024 * 1024) == "1.0 MB"
    assert human_size(1024**3) == "1.0 GB"
    assert format_mtime(None) == "-"
    assert format_mtime(1_700_000_000).count(":") == 1


def test_file_record_from_path_with_spaces_unicode_symlink(tmp_path: Path) -> None:
    target = tmp_path / "catatan ä.txt"
    target.write_text("unicode", encoding="utf-8")
    link = tmp_path / "link to note"
    link.symlink_to(target)

    record = FileRecord.from_path(target)
    assert record.name == "catatan ä.txt"
    assert record.kind is FileKind.TEXT
    assert record.size == len("unicode")
    assert record.is_symlink is False

    linked = FileRecord.from_path(link)
    assert linked.is_symlink is True
    assert linked.kind is FileKind.TEXT
    assert linked.link_target == str(target)
    assert linked.path == link


def test_broken_symlink_is_a_safe_other_record(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.symlink_to(tmp_path / "does-not-exist")
    record = FileRecord.from_path(broken)
    assert record.kind is FileKind.OTHER
    assert record.is_symlink is True
    assert record.size is not None


def test_build_file_records_real_directory(media_tree: Path) -> None:
    records = build_file_records(media_tree)
    names = [record.name for record in records]
    assert "alpha.txt" in names
    assert "project" in names
    assert "space file.txt" in names
    assert "catatan ä.txt" in names
    by_name = {record.name: record for record in records}
    assert by_name["project"].kind is FileKind.DIRECTORY
    assert by_name["project"].size is None
    assert by_name["project"].display_size == "-"
    assert by_name["photo.png"].kind is FileKind.IMAGE
    assert by_name["clip.mp4"].kind is FileKind.VIDEO
    assert by_name["archive.bin"].kind is FileKind.OTHER


def test_build_file_records_is_one_dimensional_indexable_list(media_tree: Path) -> None:
    records = build_file_records(media_tree)
    assert isinstance(records, list)
    assert records[0].path.is_absolute()
    assert len(records) == len(list(records))
    assert all(isinstance(record, FileRecord) for record in records)


def test_hidden_entries_can_be_excluded(tmp_path: Path) -> None:
    (tmp_path / ".hidden").write_text("secret", encoding="utf-8")
    (tmp_path / "visible").write_text("ok", encoding="utf-8")
    visible = build_file_records(tmp_path, include_hidden=False)
    assert [record.name for record in visible] == ["visible"]


def test_build_file_records_invalid_paths(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert build_file_records(empty) == []
    with pytest.raises(FileNotFoundError):
        build_file_records(tmp_path / "absent")
    file_path = tmp_path / "plain.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        build_file_records(file_path)


def _record(name: str, size: int | None, kind: FileKind, mtime: float) -> FileRecord:
    return FileRecord(
        path=Path("/tmp") / name,
        name=name,
        kind=kind,
        size=size,
        mtime=mtime,
    )


def test_sort_records_all_keys_and_reverse() -> None:
    records = [
        _record("zeta.txt", 300, FileKind.TEXT, 30.0),
        _record("Alpha.md", 100, FileKind.MARKDOWN, 10.0),
        _record("folder", None, FileKind.DIRECTORY, 20.0),
    ]
    assert [r.name for r in sort_records(records, "name")] == [
        "Alpha.md",
        "folder",
        "zeta.txt",
    ]
    assert [r.name for r in sort_records(records, "size")] == [
        "folder",
        "Alpha.md",
        "zeta.txt",
    ]
    assert [r.name for r in sort_records(records, "size", reverse=True)] == [
        "zeta.txt",
        "Alpha.md",
        "folder",
    ]
    assert [r.name for r in sort_records(records, "type")] == [
        "folder",
        "Alpha.md",
        "zeta.txt",
    ]
    assert [r.name for r in sort_records(records, "mtime")] == [
        "Alpha.md",
        "folder",
        "zeta.txt",
    ]
    with pytest.raises(ValueError):
        sort_records(records, "bogus")


@pytest.mark.parametrize("key", ["size", "type", "mtime"])
def test_sort_records_uses_exact_name_after_casefold_tie(key: str) -> None:
    records = [
        _record("beta.txt", 10, FileKind.TEXT, 1.0),
        _record("Alpha.txt", 10, FileKind.TEXT, 1.0),
        _record("alpha.txt", 10, FileKind.TEXT, 1.0),
    ]
    assert [r.name for r in sort_records(records, key)] == [
        "Alpha.txt",
        "alpha.txt",
        "beta.txt",
    ]


def test_list_insert_remove_and_index_helpers() -> None:
    first = _record("a.txt", 1, FileKind.TEXT, 1.0)
    second = _record("b.txt", 2, FileKind.TEXT, 2.0)
    third = _record("c.txt", 3, FileKind.TEXT, 3.0)
    records = [first, third]
    insert_record(records, 1, second)
    assert records == [first, second, third]
    assert index_of_path(records, "/tmp/b.txt") == 1
    assert index_of_path(records, "/tmp/nope.txt") is None
    removed = remove_record(records, 1)
    assert removed is second
    assert records == [first, third]


def test_permission_denied_subdirectory_is_not_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # build_file_records allows individual entries to be skipped if stat fails.
    victim = tmp_path / "victim"
    victim.write_text("x", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")

    def failing_from_path(path: Path | str) -> FileRecord:
        if Path(path).name == "victim":
            raise PermissionError("nope")
        return FileRecord(
            path=Path(path),
            name=Path(path).name,
            kind=FileKind.TEXT,
            size=1,
            mtime=0.0,
        )

    monkeypatch.setattr("pewwterm.models.FileRecord.from_path", staticmethod(failing_from_path))
    records = build_file_records(tmp_path)
    assert [record.name for record in records] == ["ok.txt"]

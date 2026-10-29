"""Tests for linear partial search and binary exact search."""

from __future__ import annotations

from pathlib import Path

import pytest

from pewwterm.models import FileKind, FileRecord
from pewwterm.search import binary_search, binary_search_all, linear_search


def _record(name: str) -> FileRecord:
    return FileRecord(
        path=Path("/tmp") / name,
        name=name,
        kind=FileKind.TEXT,
        size=1,
        mtime=0.0,
    )


RECORDS = [
    _record("wallpaper.png"),
    _record("demo.mp4"),
    _record("Wallpaper notes.txt"),
    _record("catatan.pdf"),
    _record("README.md"),
    _record("wallpaper.png"),  # duplicate display name is possible in search results
]


def test_linear_search_partial_multiple_and_case_insensitive() -> None:
    results = linear_search(RECORDS, "wall")
    assert [record.name for record in results] == [
        "wallpaper.png",
        "Wallpaper notes.txt",
        "wallpaper.png",
    ]


def test_linear_search_uppercase_query_and_substring() -> None:
    assert [r.name for r in linear_search(RECORDS, "DEMO")] == ["demo.mp4"]
    assert [r.name for r in linear_search(RECORDS, "aper.pn")] == [
        "wallpaper.png",
        "wallpaper.png",
    ]


def test_linear_search_no_results_and_empty_query() -> None:
    assert linear_search(RECORDS, "zzzz") == []
    assert linear_search([], "anything") == []
    assert linear_search(RECORDS, "") == RECORDS
    assert linear_search(RECORDS, "   ") == RECORDS
    assert linear_search(RECORDS, "").copy() is not RECORDS


def test_binary_search_exact_success_and_missing() -> None:
    names = sorted(["alpha.txt", "beta.txt", "gamma.txt"])
    assert binary_search(names, "beta.txt") == 1
    assert binary_search(names, "BETA.TXT") == 1
    assert binary_search(names, "delta.txt") == -1
    assert binary_search([], "anything") == -1
    assert binary_search(names, "BETA.TXT", case_sensitive=True) == -1


def test_binary_search_duplicate_names_returns_first() -> None:
    names = ["a.txt", "b.txt", "b.txt", "b.txt", "c.txt"]
    assert binary_search(names, "b.txt") == 1
    assert binary_search_all(names, "b.txt") == [1, 2, 3]
    assert binary_search_all(names, "B.TXT") == [1, 2, 3]
    assert binary_search_all(names, "missing") == []


def test_binary_search_precondition_rejects_unsorted_input() -> None:
    with pytest.raises(ValueError, match="sorted"):
        binary_search(["zeta", "alpha"], "alpha")


def test_binary_search_single_and_boundaries() -> None:
    names = ["alpha", "omega"]
    assert binary_search(names, "alpha") == 0
    assert binary_search(names, "omega") == 1
    assert binary_search(names, "a") == -1
    assert binary_search(names, "zzz") == -1


def test_binary_search_case_sensitive_success() -> None:
    names = sorted(["Alpha", "beta", "Gamma"])  # ASCII sort: uppercase first
    assert binary_search(names, "Alpha", case_sensitive=True) == 0
    assert binary_search(names, "alpha", case_sensitive=True) == -1

"""Filename search algorithms used by the TUI.

Two intentionally different algorithms are implemented:

``linear_search``
    Scans the one-dimensional record list from start to end, comparing a
    case-folded query against each filename.  It supports partial matches and
    returns *all* matches.  Time complexity is O(n) per query and it needs no
    ordering.

``binary_search``
    Finds an exact filename in an already sorted list of names.  It uses
    case-folded comparisons and returns the index of the **first** duplicate.
    Time complexity is O(log n), but it has a strict precondition: the list must
    be sorted according to the same key.  ``binary_search`` validates this in
    O(n) while raising ``ValueError`` for unsorted input; the validation is a
    teaching/diagnostic aid, so production callers can pre-sort once.

Why both?
    The interactive search box must match fragments ("wall" -> wallpaper.png) and
    show multiple hits, which binary search cannot do.  Exact lookups over an
    indexed name list benefit from binary search; ``binary_search_all`` expands
    around the found index to include duplicate names.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import FileRecord


def linear_search(records: list[FileRecord], query: str) -> list[FileRecord]:
    """Return every record whose filename contains *query*, ignoring case.

    A blank/whitespace-only query returns the entire collection, which lets the
    UI show the current directory while the search box is empty.  The input list
    is not modified and results keep its order.

    Complexity: O(n * m) for n filenames of average length m, effectively O(n)
    for short queries.
    """

    needle = query.strip().casefold()
    if not needle:
        return list(records)
    matches: list[FileRecord] = []
    for record in records:  # linear iteration over the one-dimensional list
        if needle in record.name.casefold():
            matches.append(record)
    return matches


def _comparison_key(value: str, case_sensitive: bool) -> str:
    return value if case_sensitive else value.casefold()


def binary_search(
    sorted_names: Sequence[str],
    target: str,
    *,
    case_sensitive: bool = False,
) -> int:
    """Find an exact name in a sorted sequence and return its first index.

    Returns ``-1`` when the target is absent.  The precondition is that
    ``sorted_names`` is ascending under the same comparison mode.  Unsorted input
    raises :class:`ValueError` instead of returning a misleading answer.

    Complexity: O(log n) for the search plus O(n) for the precondition check.
    """

    key = lambda value: _comparison_key(value, case_sensitive)  # noqa: E731
    for left, right in zip(sorted_names, sorted_names[1:]):
        if key(left) > key(right):
            raise ValueError("binary_search requires a sorted sequence")
    needle = key(target)
    low, high = 0, len(sorted_names) - 1
    found = -1
    while low <= high:
        middle = (low + high) // 2
        candidate = key(sorted_names[middle])
        if candidate == needle:
            found = middle
            high = middle - 1  # keep searching left for the first duplicate
        elif candidate < needle:
            low = middle + 1
        else:
            high = middle - 1
    return found


def binary_search_all(
    sorted_names: Sequence[str],
    target: str,
    *,
    case_sensitive: bool = False,
) -> list[int]:
    """Return all indices with an exact name, using binary search as the entry.

    Duplicate names are valid; after finding one match we scan outward.  In the
    worst case (every name equal) this is O(n), which is unavoidable because the
    output itself is O(n).  An empty list means no exact match.
    """

    index = binary_search(sorted_names, target, case_sensitive=case_sensitive)
    if index < 0:
        return []
    key = lambda value: _comparison_key(value, case_sensitive)  # noqa: E731
    needle = key(target)
    start = index
    while start > 0 and key(sorted_names[start - 1]) == needle:
        start -= 1
    end = index + 1
    while end < len(sorted_names) and key(sorted_names[end]) == needle:
        end += 1
    return list(range(start, end))

import math
from typing import Any, Iterable


def merge_adjacent_spans(spans: Iterable[tuple[int, int]]) -> Iterable[tuple[int, int]]:
    merged_start, merged_end = None, None

    for start, end in spans:
        if merged_start is None:
            merged_start, merged_end = start, end
        elif merged_end == start:
            merged_end = end
        else:
            yield merged_start, merged_end
            merged_start, merged_end = start, end

    if merged_start is not None:
        yield merged_start, merged_end  # type: ignore


def generate_missing_spans(
    start: int, end: int, existing_spans: Iterable[tuple[int, int]]
) -> Iterable[tuple[int, int]]:
    # Initially assume entire span missing.
    missing_start, missing_end = start, end

    # Spans are ordered by start_date. Spans do not overlap with each other.
    for existing_start, existing_end in existing_spans:
        if existing_start > missing_start:
            yield missing_start, existing_start
        missing_start = existing_end

    if missing_start < missing_end:
        yield missing_start, missing_end


def page(start: int, end: int, step: int) -> Iterable[tuple[int, int]]:
    for page_start in range(start, end, step):
        page_end = min(page_start + step, end)
        yield page_start, page_end


def page_limit(start: int, end: int, interval: int, limit: int) -> Iterable[tuple[int, int]]:
    total_size = (end - start) / interval
    max_count = limit * interval
    page_size = math.ceil(total_size / limit)
    for i in range(0, page_size):
        page_start = start + i * max_count
        page_end = min(page_start + max_count, end)
        yield page_start, page_end


# Ref: https://stackoverflow.com/a/38397347/1466456
def recursive_iter(obj: Any, keys: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from recursive_iter(v, keys + (k,))
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            yield from recursive_iter(item, keys + (idx,))
    else:
        yield keys, obj

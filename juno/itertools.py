import math
from typing import Any, Iterable, List, Tuple, TypeVar, Union, overload

T = TypeVar('T')


def merge_adjacent_spans(spans: Iterable[Tuple[int, int]]) -> Iterable[Tuple[int, int]]:
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


def generate_missing_spans(start: int, end: int,
                           existing_spans: Iterable[Tuple[int, int]]) -> Iterable[Tuple[int, int]]:
    # Initially assume entire span missing.
    missing_start, missing_end = start, end

    # Spans are ordered by start_date. Spans do not overlap with each other.
    for existing_start, existing_end in existing_spans:
        if existing_start > missing_start:
            yield missing_start, existing_start
        missing_start = existing_end

    if missing_start < missing_end:
        yield missing_start, missing_end


def page(start: int, end: int, interval: int, limit: int) -> Iterable[Tuple[int, int]]:
    total_size = (end - start) / interval
    max_count = limit * interval
    page_size = math.ceil(total_size / limit)
    for i in range(0, page_size):
        page_start = start + i * max_count
        page_end = min(page_start + max_count, end)
        yield page_start, page_end


# Ref: https://stackoverflow.com/a/38397347/1466456
def recursive_iter(obj: Any, keys: Tuple[Any, ...] = ()) -> Iterable[Tuple[Tuple[Any, ...], Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from recursive_iter(v, keys + (k, ))
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            yield from recursive_iter(item, keys + (idx, ))
    else:
        yield keys, obj


# TODO: Use `recursive_iter` instead?
# Ref: https://stackoverflow.com/a/10632356/1466456
def flatten(items: Iterable[Union[T, List[T]]]) -> Iterable[T]:
    for item in items:
        if isinstance(item, (list, tuple)):
            for subitem in item:
                yield subitem
        else:
            yield item


@overload
def chunks(seq: List[T], n: int) -> Iterable[List[T]]:
    ...


@overload
def chunks(seq: str, n: int) -> Iterable[str]:
    ...


# Ref: https://stackoverflow.com/a/312464/1466456
def chunks(seq, n):
    """Yield successive n-sized chunks from l."""
    length = len(seq)
    if length <= n:
        yield seq
    else:
        for i in range(0, length, n):
            yield seq[i:i + n]

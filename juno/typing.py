from __future__ import annotations

from collections import deque
from typing import (
    Any,
    Iterable,
    Literal,
    Optional,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)


def get_input_type_hints(obj: Any) -> dict[str, Any]:
    return {n: t for n, t in get_type_hints(obj).items() if n != "return"}


def get_name(type_: Any) -> str:
    return str(type_) if get_origin(type_) else type_.__name__


def get_root_origin(type_: Any) -> Optional[type[Any]]:
    last_origin = None
    origin = type_
    while True:
        origin = get_origin(origin)
        if origin is None:
            break
        else:
            last_origin = origin
    return last_origin


def types_match(obj: Any, type_: type[Any]) -> bool:
    origin = get_root_origin(type_) or type_

    if origin is Literal:
        args = get_args(type_)
        return obj in args

    if origin is Union:
        args = get_args(type_)
        return any(types_match(obj, sub_type) for sub_type in args)

    if type(origin) is TypeVar:
        return types_match(obj, type(obj))

    if not isinstance(obj, origin):
        return False

    if isinstance(obj, tuple):
        if origin:  # Tuple.
            return all(types_match(so, st) for so, st, in zip(obj, get_args(type_)))
        else:  # Named tuple.
            return all(types_match(so, st) for so, st in zip(obj, get_type_hints(type_).values()))

    if isinstance(obj, dict):
        assert origin
        key_type, value_type = get_args(type_)
        return all(types_match(k, key_type) and types_match(v, value_type) for k, v in obj.items())

    if isinstance(obj, (list, deque)):
        assert origin
        (subtype,) = get_args(type_)
        return all(types_match(so, subtype) for so in obj)

    # Try matching for a regular dataclass.
    return all(types_match(getattr(obj, sn), st) for sn, st in get_type_hints(origin).items())


def map_input_args(obj: Any, args: Iterable[Any]) -> dict[str, Any]:
    return {k: v for k, v in zip(get_input_type_hints(obj).keys(), args)}


def resolve_generic_types(container: Any) -> list[type]:
    result = []
    container_type = type(container)
    generic_params = container_type.__parameters__
    type_hints = get_type_hints(container_type)
    for generic_param in generic_params:
        name = next(k for k, v in type_hints.items() if v is generic_param)
        result.append(type(getattr(container, name)))
    return result

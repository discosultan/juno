import inspect
from collections import deque
from decimal import Decimal
from enum import Enum
from types import TracebackType
from typing import (
    Any, Dict, Iterable, List, Optional, Type, TypeVar, Union, get_args, get_origin,
    get_type_hints
)

from typing_inspect import get_parameters, is_generic_type, is_optional_type, is_typevar

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]


def get_input_type_hints(obj: Any) -> Dict[str, type]:
    return {n: t for n, t in get_type_hints(obj).items() if n != 'return'}


def get_name(type_: Any) -> str:
    return str(type_) if get_origin(type_) else type_.__name__


def get_root_origin(type_: Any) -> Optional[Type[Any]]:
    last_origin = None
    origin = type_
    while True:
        origin = get_origin(origin)
        if origin is None:
            break
        else:
            last_origin = origin
    return last_origin


def isnamedtuple(obj: Any) -> bool:
    # Note that '_fields' is present only if the tuple has at least 1 field.
    return (
        inspect.isclass(obj)
        and issubclass(obj, tuple)
        and bool(getattr(obj, '_fields', False))
    )


def isenum(obj: Any) -> bool:
    return inspect.isclass(obj) and issubclass(obj, Enum)


def raw_to_type(value: Any, type_: Type[Any]) -> Any:
    origin = get_root_origin(type_) or type_

    # Needs to be a list because type_ can be non-hashable for lookup in a set.
    if origin in [bool, int, float, str, Decimal]:
        return value

    if origin is list:
        sub_type, = get_args(type_)
        for i, sub_value in enumerate(value):
            value[i] = raw_to_type(sub_value, sub_type)
        return value

    if origin is deque:
        sub_type, = get_args(type_)
        return deque((raw_to_type(sv, sub_type) for sv in value), maxlen=len(value))

    if origin is tuple:
        sub_types = get_args(type_)
        for i, (sub_value, sub_type) in enumerate(zip(value, sub_types)):
            value[i] = raw_to_type(sub_value, sub_type)
        return value

    if origin is dict:
        _, sub_type = get_args(type_)
        for key, sub_value in value.items():
            value[key] = raw_to_type(sub_value, sub_type)
        return value

    if origin is Union:
        sub_type, _ = get_args(type_)
        if value is None:
            return value
        return raw_to_type(value, sub_type)

    if isenum(origin):
        return origin(value)

    if isnamedtuple(type_):
        annotations = get_type_hints(type_)
        args = []
        for i, (_name, sub_type) in enumerate(annotations.items()):
            if i >= len(value):
                # Resort to default values.
                break
            sub_value = value[i]
            args.append(raw_to_type(sub_value, sub_type))
        return type_(*args)

    # Try constructing a regular dataclass.
    annotations = get_type_hints(origin)
    type_args_map = {p: a for p, a in zip(get_parameters(origin), get_args(type_))}
    instance = origin.__new__(origin)  # type: ignore
    for name, sub_type in ((k, v) for k, v in annotations.items() if k in annotations):
        if name not in value:
            continue
        # Substitute generics.
        # TODO: Generalize
        if is_typevar(sub_type):
            sub_type = type_args_map[sub_type]
        if is_optional_type(sub_type):
            sub_type_arg, _ = get_args(sub_type)
            if is_typevar(sub_type_arg):
                sub_type = Optional[type_args_map[sub_type_arg]]
        if is_generic_type(sub_type):
            sub_type_args = get_args(sub_type)
            if len(sub_type_args) == 1 and is_typevar(sub_type_args[0]):
                sub_type = sub_type[type_args_map[sub_type_args[0]]]
        sub_value = value[name]
        setattr(instance, name, raw_to_type(sub_value, sub_type))
    return instance


def types_match(obj: Any, type_: Type[Any]):
    origin = get_root_origin(type_) or type_

    if origin is Union:
        sub_type, _ = get_args(type_)
        return obj is None or types_match(obj, sub_type)

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
        subtype, = get_args(type_)
        return all(types_match(so, subtype) for so in obj)

    # Try matching for a regular dataclass.
    return all(
        types_match(
            getattr(obj, sn), st
        ) for sn, st in get_type_hints(origin).items()
    )


def map_input_args(obj: Any, args: Iterable[Any]) -> Dict[str, Any]:
    return {k: v for k, v in zip(get_input_type_hints(obj).keys(), args)}

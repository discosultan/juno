from decimal import Decimal
from types import TracebackType
from typing import Any, Dict, List, Optional, Type, Union, get_args, get_origin, get_type_hints

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]


def get_input_type_hints(obj: Any) -> Dict[str, type]:
    return {n: t for n, t in get_type_hints(obj).items() if n != 'return'}


def get_name(type_: Any) -> str:
    return str(type_) if get_origin(type_) else type_.__name__


def isnamedtuple(obj: Any) -> bool:
    origin = get_origin(obj) or obj
    # Note that '_fields' is present only if the tuple has at least 1 field.
    return issubclass(origin, tuple) and bool(getattr(origin, '_fields', False))


def isoptional(obj: Any) -> bool:
    return get_origin(obj) is Union and type(None) in get_args(obj)


def types_match(obj: Any, type_: Type[Any]):
    origin = get_origin(type_) or type_
    if not isinstance(obj, origin):
        return False

    if origin in [bool, int, float, str, Decimal]:
        return True

    if isinstance(obj, tuple):
        if origin:  # Not named tuple.
            return all(types_match(so, st) for so, st, in zip(obj, get_args(type_)))
        else:  # Named tuple.
            return all(types_match(so, st) for so, st in zip(obj, get_type_hints(type_).values()))
    elif isinstance(obj, dict):
        assert origin
        key_type, value_type = get_args(type_)
        return all(types_match(k, key_type) and types_match(v, value_type) for k, v in obj.items())
    elif isinstance(obj, list):
        assert origin
        subtype, = get_args(type_)
        return all(types_match(so, subtype) for so in obj)
    else:
        raise NotImplementedError(f'Type matching not implemented for {type_}')

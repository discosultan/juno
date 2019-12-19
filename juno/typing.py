from types import TracebackType
from typing import Any, Dict, List, Optional, Type, Union, get_origin, get_type_hints

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]


def get_input_type_hints(obj: Any) -> Dict[str, type]:
    return {n: t for n, t in get_type_hints(obj).items() if n != 'return'}


def filter_member_args(obj: Any, dict_: Dict[str, Any]) -> Dict[str, Any]:
    keys = set(get_input_type_hints(obj).keys())
    return {k: v for k, v in dict_.items() if k in keys}


def get_name(type_: Any) -> str:
    return str(type_) if get_origin(type_) else type_.__name__


def isnamedtuple(object: Any) -> bool:
    origin = get_origin(object) or object
    # Note that '_fields' is present only if the tuple has at least 1 field.
    return issubclass(origin, tuple) and bool(getattr(origin, '_fields', False))

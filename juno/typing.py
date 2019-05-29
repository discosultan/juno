from types import TracebackType
from typing import Any, Dict, List, NewType, Optional, Type, Union, get_type_hints

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]

Interval = NewType('Interval', int)
Timestamp = NewType('Timestamp', int)


def get_input_type_hints(obj: Any) -> Dict[str, type]:
    return {n: t for n, t in get_type_hints(obj).items() if n != 'return'}


def filter_member_args(obj: Any, dict_: Dict[str, Any]) -> Dict[str, Any]:
    keys = set(get_input_type_hints(obj).keys())
    return {k: v for k, v in dict_.items() if k in keys}

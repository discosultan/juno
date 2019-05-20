from types import TracebackType
from typing import Any, Dict, List, NewType, Optional, Type, TypeVar, Union, get_type_hints

T = TypeVar('T')

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]

Interval = NewType('Interval', int)
Timestamp = NewType('Timestamp', int)


def get_input_type_hints(obj: Any) -> Dict[str, type]:
    return {n: t for n, t in get_type_hints(obj).items() if n != 'return'}

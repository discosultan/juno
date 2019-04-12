from types import TracebackType
from typing import Any, Dict, List, NewType, Optional, Type, Union

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]

Interval = NewType('Interval', int)
Timestamp = NewType('Timestamp', int)

from types import TracebackType
from typing import Optional, Type

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

import contextlib
from types import TracebackType
from typing import Optional


class AsyncContextManager(contextlib.AbstractAsyncContextManager):
    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        pass

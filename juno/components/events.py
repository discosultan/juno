import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from juno.utils import exc_traceback

_log = logging.getLogger(__name__)


class Events:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], list[Callable[..., Awaitable[None]]]] = (
            defaultdict(list)
        )

    def on(self, channel: str, event: str) -> Callable[[Callable[..., Awaitable[None]]], None]:
        def _on(func: Callable[..., Awaitable[None]]) -> None:
            self._handlers[(channel, event)].append(func)

        return _on

    async def emit(self, channel: str, event: str, *args: Any) -> list[Any]:
        handlers = self._handlers[(channel, event)]
        results = await asyncio.gather(*(h(*args) for h in handlers), return_exceptions=True)
        for e in (r for r in results if isinstance(r, Exception)):
            _log.error(exc_traceback(e))
        return results

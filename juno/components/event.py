import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Tuple


class Event:
    def __init__(self) -> None:
        self._handlers: Dict[Tuple[str, str], List[Callable[..., Awaitable[None]]]] = (
            defaultdict(list)
        )

    def on(self, channel: str, event: str) -> Callable[[Callable[..., Awaitable[None]]], None]:
        def _on(func: Callable[..., Awaitable[None]]) -> None:
            self._handlers[(channel, event)].append(func)

        return _on

    async def emit(self, channel: str, event: str, *args: Any) -> List[Any]:
        return await asyncio.gather(
            *(x(*args) for x in self._handlers[(channel, event)]), return_exceptions=True
        )

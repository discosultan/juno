from __future__ import annotations

from typing import Any, Awaitable, Callable, List

from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import EventEmitter


class Agent:

    required_components: List[str] = []
    run: Callable[..., Awaitable[Any]]

    async def __aenter__(self) -> Agent:
        self.ee = EventEmitter()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

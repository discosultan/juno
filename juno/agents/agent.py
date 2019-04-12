from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import EventEmitter


class Agent:

    required_components: List[str] = []
    run: Callable[..., Awaitable[Any]]

    def __init__(self, components: Dict[str, Any], agent_config: Dict[str, Any]) -> None:
        self.components = components
        self.config = agent_config

    async def __aenter__(self) -> Agent:
        self.ee = EventEmitter()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    async def start(self) -> Any:
        return await self.run(**{k: v for k, v in self.config.items() if k != 'name'})

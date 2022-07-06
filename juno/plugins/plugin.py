from abc import ABC, abstractmethod

from juno.contextlib import AsyncContextManager


class Plugin(AsyncContextManager, ABC):
    @abstractmethod
    async def activate(self, agent_name: str, agent_type: str) -> None:
        pass

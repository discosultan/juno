from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager


class Plugin(AbstractAsyncContextManager, ABC):
    @abstractmethod
    async def activate(self, agent_name: str, agent_type: str) -> None:
        pass

from abc import ABC, abstractmethod


class Plugin(ABC):
    @abstractmethod
    async def activate(self, agent_name: str, agent_type: str) -> None:
        pass

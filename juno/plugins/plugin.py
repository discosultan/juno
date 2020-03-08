from typing import Type

from juno.agents import Agent


class Plugin:
    async def activate(self, agent_name: str, agent_type: Type[Agent]) -> None:
        pass

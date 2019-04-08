from typing import Any, List

from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import EventEmitter


class Agent:

    required_components: List[str] = []

    async def __aenter__(self):
        self.ee = EventEmitter()

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    async def run(**kwargs: Any) -> None:
        pass

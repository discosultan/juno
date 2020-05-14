from abc import ABC, abstractmethod
from typing import Any, Optional

from juno.brokers import Broker
from juno.trading import TradingSummary


class Trader(ABC):
    Config: Any
    State: Any

    @property
    @abstractmethod
    def broker(self) -> Broker:
        pass

    @abstractmethod
    async def run(self, config: Any, state: Optional[Any] = None) -> TradingSummary:
        pass

from abc import ABC, abstractmethod

from juno.assets import ExchangeInfo


class Exchange(ABC):
    @abstractmethod
    async def get_exchange_info(self) -> ExchangeInfo:
        pass

from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict

from juno import Advice, Candle


class Strategy(ABC):

    @abstractproperty
    def req_history(self) -> int:
        pass

    @staticmethod
    @abstractmethod
    def meta() -> Dict[Any, Any]:
        pass

    @abstractmethod
    def update(self, candle: Candle) -> Advice:
        pass

from abc import ABC, abstractmethod, abstractproperty

from juno import Candle


class Strategy(ABC):

    @abstractproperty
    def req_history(self) -> int:
        pass

    @abstractmethod
    def update(self, candle: Candle) -> int:
        pass

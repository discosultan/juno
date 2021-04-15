from abc import ABC, abstractmethod

from juno.tickers import Ticker


class Exchange(ABC):
    # Capabilities.
    can_list_all_tickers: bool = False  # Accepts empty symbols filter to retrieve all tickers.

    @abstractmethod
    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        # Empty list to disable filter.
        pass

from __future__ import annotations

from abc import ABC, abstractmethod

from juno.assets.models import ExchangeInfo, Ticker


class Exchange(ABC):
    can_list_all_tickers: bool = False  # Accepts empty symbols filter to retrieve all tickers.

    @abstractmethod
    async def get_exchange_info(self) -> ExchangeInfo:
        pass

    # TODO: abstract?
    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        # Empty list to disable filter.
        pass

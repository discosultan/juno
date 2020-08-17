import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Optional

from juno.brokers import Broker
from juno.components import Wallet
from juno.trading import TradingMode, TradingSummary

_log = logging.getLogger(__name__)


class Trader(ABC):
    Config: Any
    State: Any

    @property
    @abstractmethod
    def broker(self) -> Broker:
        pass

    @property
    @abstractmethod
    def wallet(self) -> Wallet:
        pass

    @abstractmethod
    async def run(self, config: Any, state: Optional[Any] = None) -> TradingSummary:
        pass

    def request_quote(
        self, quote: Optional[Decimal], exchange: str, asset: str, mode: TradingMode
    ) -> Decimal:
        if mode in [TradingMode.BACKTEST, TradingMode.PAPER]:
            if quote is None:
                raise ValueError('Quote must be specified when backtesting or paper trading')
            return quote

        available_quote = self.wallet.get_balance(exchange, asset, 'spot').available

        if quote is None:
            _log.info(f'quote not specified; using available {available_quote} {asset}')
            return available_quote

        if available_quote < quote:
            raise ValueError(
                f'Requesting trading with {quote} {asset} but only {available_quote} available'
            )

        return quote

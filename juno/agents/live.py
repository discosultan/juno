import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from juno import Interval, Timestamp, strategies
from juno.components import Informant, Wallet
from juno.config import get_module_type_and_config
from juno.math import floor_multiple
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import MissedCandlePolicy, Trader, TradingSummary
from juno.utils import format_as_config, unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Live(Agent):
    def __init__(self, informant: Informant, wallet: Wallet, trader: Trader) -> None:
        super().__init__()
        self._informant = informant
        self._wallet = wallet
        self._trader = trader

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        strategy: Dict[str, Any],
        quote: Optional[Decimal] = None,
        end: Timestamp = MAX_TIME_MS,
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
        get_time_ms: Optional[Callable[[], int]] = None
    ) -> None:
        if not get_time_ms:
            get_time_ms = time_ms

        current = floor_multiple(get_time_ms(), interval)
        end = floor_multiple(end, interval)
        assert end > current

        _, quote_asset = unpack_symbol(symbol)
        available_quote = self._wallet.get_balance(exchange, quote_asset).available

        _, filters = self._informant.get_fees_filters(exchange, symbol)
        assert available_quote > filters.price.min

        if quote is None:
            quote = available_quote
            _log.info(f'quote not defined; using available {available_quote} {quote_asset}')
        else:
            assert quote <= available_quote
            _log.info(f'using pre-defined quote {quote} {quote_asset}')

        strategy_type, strategy_config = get_module_type_and_config(strategies, strategy)
        self.result = TradingSummary(start=current, quote=quote)
        await self._trader.run(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=current,
            end=end,
            quote=quote,
            strategy_type=strategy_type,
            strategy_kwargs=strategy_config,
            test=False,
            event=self,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
            summary=self.result
        )

    def on_finally(self) -> None:
        _log.info(f'trading summary: {format_as_config(self.result)}')

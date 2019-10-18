import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from juno.brokers import Broker
from juno.components import Chandler, Informant, Wallet
from juno.math import floor_multiple
from juno.strategies import new_strategy
from juno.time import MAX_TIME_MS, time_ms
from juno.trading import TradingLoop
from juno.utils import unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Live(Agent):
    def __init__(
        self, chandler: Chandler, informant: Informant, wallet: Wallet, broker: Broker
    ) -> None:
        super().__init__()
        self.chandler = chandler
        self.informant = informant
        self.wallet = wallet
        self.broker = broker

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        strategy_config: Dict[str, Any],
        end: int = MAX_TIME_MS,
        restart_on_missed_candle: bool = False,
        adjust_start: bool = True,
        trailing_stop: Optional[Decimal] = None,
        get_time: Optional[Callable[[], int]] = None
    ) -> None:
        if not get_time:
            get_time = time_ms

        now = floor_multiple(get_time(), interval)
        assert end > now

        _, quote_asset = unpack_symbol(symbol)
        quote = self.wallet.get_balance(exchange, quote_asset).available

        _, filters = self.informant.get_fees_filters(exchange, symbol)
        assert quote > filters.price.min

        trading_loop = TradingLoop(
            chandler=self.chandler,
            informant=self.informant,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=now,
            end=end,
            quote=quote,
            new_strategy=lambda: new_strategy(strategy_config),
            broker=self.broker,
            test=False,
            event=self,
            log=_log,
            restart_on_missed_candle=restart_on_missed_candle,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
        )
        self.result = trading_loop.summary
        await trading_loop.run()

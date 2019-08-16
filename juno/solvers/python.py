from typing import List, Type

from juno import Advice, Candle, Fees
from juno.filters import Filters
from juno.strategies import Strategy


class Python:
    def __init__(self, candles: List[Candle], fees: Fees, filters: Filters,
                 strategy_type: Type[Strategy], quote) -> None:
        self.candles = candles
        self.fees = fees
        self.filters = filters
        self.strategy_type = strategy_type
        self.quote = quote

    def solve(self, *args: Any) -> Any:
        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        self.quote = quote

        self.fees = fees
        self.filters = filters
        self.result = TradingSummary(
            interval=interval,
            start=start,
            quote=quote,
            fees=self.fees,
            filters=self.filters
        )
        self.open_position = None
        restart_count = 0

        while True:
            self.last_candle = None
            restart = False

            strategy = new_strategy(strategy_config)

            if restart_count == 0:
                start -= strategy.req_history * interval

            for candle in candles:
                if not candle.closed:
                    continue

                self.result.append_candle(candle)

                if self.last_candle and candle.time - self.last_candle.time >= interval * 2:
                    if restart_on_missed_candle:
                        start = candle.time
                        restart = True
                        restart_count += 1
                        break

                self.last_candle = candle
                advice = strategy.update(candle)

                if not self.open_position and advice is Advice.BUY:
                    if not self._try_open_position(candle):
                        break
                elif self.open_position and advice is Advice.SELL:
                    self._close_position(candle)

            if not restart:
                break

        return self.result
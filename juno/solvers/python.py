from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional, Type

from juno import Advice, Candle, Fees, Fill, Fills, Filters, Position, TradingSummary
from juno.strategies import Strategy
from juno.utils import unpack_symbol


class Python:
    def __init__(self, candles: List[Candle], fees: Fees, filters: Filters,
                 strategy_type: Type[Strategy], symbol: str, interval: int,
                 start: int, end: int, quote: Decimal) -> None:
        self.candles = candles
        self.fees = fees
        self.filters = filters
        self.strategy_type = strategy_type
        self.base_asset, self.quote_asset = unpack_symbol(symbol)
        self.interval = interval
        self.start = start
        self.end = end
        self.quote = quote
        self.restart_on_missed_candle = False
        self.open_position: Optional[Position] = None

    async def __aenter__(self) -> Python:
        return self

    def solve(self, *args: Any) -> Any:
        self.result = TradingSummary(
            interval=self.interval,
            start=self.start,
            quote=self.quote,
            fees=self.fees,
            filters=self.filters
        )

        self.open_position = None

        while True:
            self.last_candle = None
            restart = False

            strategy = self.strategy_type(*args)  # type: ignore

            for candle in self.candles:
                if not candle.closed:
                    continue

                self.result.append_candle(candle)

                if self.last_candle and candle.time - self.last_candle.time >= self.interval * 2:
                    if self.restart_on_missed_candle:
                        restart = True
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

        return (
            float(self.result.profit),
            float(self.result.mean_drawdown),
            float(self.result.max_drawdown),
            float(self.result.mean_position_profit),
            self.result.mean_position_duration,
        )

    def _try_open_position(self, candle: Candle) -> bool:
        price = candle.close

        size = self.filters.size.round_down(self.quote / price)
        if size == 0:
            return False

        fee = size * self.fees.taker

        self.open_position = Position(
            time=candle.time,
            fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.base_asset)])
        )

        self.quote -= size * price

        return True

    def _close_position(self, candle: Candle) -> None:
        assert self.open_position

        price = candle.close

        size = self.filters.size.round_down(
            self.open_position.total_size - self.open_position.fills.total_fee
        )

        quote = size * price
        fee = quote * self.fees.taker

        self.open_position.close(
            time=candle.time,
            fills=Fills([Fill(price=price, size=size, fee=fee, fee_asset=self.quote_asset)])
        )
        self.result.append_position(self.open_position)
        self.open_position = None

        self.quote = quote - fee

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncIterable, AsyncIterator, Optional

from juno import Balance, Candle, Fill, OrderResult, OrderType, OrderUpdate, Side, TimeInForce
from juno.common import OrderStatus
from juno.exchanges.binance import Binance


class FakeBinance(Binance):
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        high_precision: bool = True,
        balances: dict[str, Decimal] = {},
    ) -> None:
        super().__init__(api_key=api_key, secret_key=secret_key, high_precision=high_precision)
        self._balances = balances
        self._time = 0
        self._last_prices = {}

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        if account != "spot":
            raise NotImplementedError()
        return {
            "spot": {key: Balance(available=value) for key, value in self._balances.items()}
        }

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        pass

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        pass

    async def place_order(
        self,
        account: str,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
    ) -> OrderResult:
        if type_ is not OrderType.MARKET:
            raise NotImplementedError()
        
        price=self._last_prices[symbol]
        return OrderResult(self._time, OrderStatus.FILLED, fills=[Fill(
            price=price,
            size=
        )])

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        pass

    async def stream_historical_candles(
        self, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        async for candle in super().stream_historical_candles(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
        ):
            self._time = max(self._time, candle.time + interval)
            yield candle

    @asynccontextmanager
    async def connect_stream_candles(
        self, symbol: str, interval: int
    ) -> AsyncIterator[AsyncIterable[Candle]]:
        async with super().connect_stream_candles(symbol=symbol, interval=interval) as stream:

            async def inner() -> AsyncIterable[Candle]:
                async for candle in stream:
                    self._time = max(self._time, candle.time + interval)
                    yield candle

            yield inner()

    async def transfer(
        self, asset: str, size: Decimal, from_account: str, to_account: str
    ) -> None:
        raise NotImplementedError()

    async def borrow(self, asset: str, size: Decimal, account) -> None:
        raise NotImplementedError()

    async def repay(self, asset: str, size: Decimal, account: str) -> None:
        raise NotImplementedError()

    async def convert_dust(self, assets: list[str]) -> None:
        raise NotImplementedError()

    async def withdraw(self, asset: str, address: str, amount: Decimal) -> None:
        raise NotImplementedError()

    async def purchase_savings_product(self, product_id: str, size: Decimal) -> None:
        raise NotImplementedError()

    async def redeem_savings_product(self, product_id: str, size: Decimal) -> None:
        raise NotImplementedError()

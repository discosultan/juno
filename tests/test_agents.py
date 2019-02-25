from decimal import Decimal

import pytest

from juno import Candle, Fees, SymbolInfo
from juno.agents import Backtest


class FakeInformant:

    def get_fees(self, exchanges: str):
        return Fees(Decimal(0), Decimal(0))

    def get_symbol_info(self, exchange, symbol):
        return SymbolInfo(
            min_size=Decimal(1), max_size=Decimal(10000), size_step=Decimal(1),
            min_price=Decimal(1), max_price=Decimal(10000), price_step=Decimal(1))

    async def stream_candles(self, exchange, symbol, interval, start, end):
        yield Candle(0, Decimal(1), Decimal(1), Decimal(1), Decimal(5), Decimal(1)), True
        yield Candle(1, Decimal(1), Decimal(1), Decimal(1), Decimal(10), Decimal(1)), True
        # Long. Size 10.
        yield Candle(2, Decimal(1), Decimal(1), Decimal(1), Decimal(30), Decimal(1)), True
        yield Candle(3, Decimal(1), Decimal(1), Decimal(1), Decimal(20), Decimal(1)), True
        # Short.
        yield Candle(4, Decimal(1), Decimal(1), Decimal(1), Decimal(40), Decimal(1)), True
        # Long. Size 5.
        yield Candle(5, Decimal(1), Decimal(1), Decimal(1), Decimal(10), Decimal(1)), True
        # Short.


@pytest.fixture
def informant():
    return FakeInformant()


async def test_backtest(loop, informant):
    agent = Backtest(components={'informant': informant})

    strategy_config = {
        'name': 'emaemacx',
        'short_period': 1,
        'long_period': 2,
        'neg_threshold': Decimal(-1),
        'pos_threshold': Decimal(1),
        'persistence': 0
    }

    # TODO: Validate output
    await agent.run(exchange='dummy', symbol='eth-btc', interval=1, start=0, end=6,
                    quote=Decimal(100), strategy_config=strategy_config)

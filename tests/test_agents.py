from decimal import Decimal

from juno import Candle, Fees, SymbolInfo
from juno.agents import Backtest
from juno.agents.backtest import Position


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


async def test_backtest(loop):
    agent = Backtest(components={'informant': FakeInformant()})

    strategy_config = {
        'name': 'emaemacx',
        'short_period': 1,
        'long_period': 2,
        'neg_threshold': Decimal(-1),
        'pos_threshold': Decimal(1),
        'persistence': 0
    }

    res = await agent.run(exchange='dummy', symbol='eth-btc', interval=1, start=0, end=6,
                          quote=Decimal(100), strategy_config=strategy_config)
    assert res.profit == -50
    assert res.potential_hodl_profit == 100
    assert res.duration == 6
    assert res.yearly_roi == -2629746000
    assert res.max_drawdown == Decimal('0.75')
    assert res.mean_drawdown == Decimal('0.25')
    assert res.mean_position_profit == -25
    assert res.mean_position_duration == 1
    assert res.start == 0
    assert res.end == 6


def test_position():
    pos = Position(0, Decimal(6), Decimal(2), Decimal(2))
    pos.close(1, Decimal(2), Decimal(2), Decimal(1))

    assert pos.cost == Decimal(12)  # 6 * 2
    assert pos.gain == Decimal(3)  # 2 * 2 - 1
    assert pos.dust == Decimal(2)  # 6 - 2 - 2
    assert pos.profit == Decimal(-9)
    assert pos.duration == 1
    assert pos.start == 0
    assert pos.end == 1
    # TODO: assert roi and yearly roi

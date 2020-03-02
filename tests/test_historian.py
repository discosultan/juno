import pytest

from juno import Candle
from juno.components import Historian

from . import fakes


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (10, 20),  # Simple happy flow.
    (0, 16),  # `final_end` and start not being over-adjusted.
])
async def test_find_first_candle(storage, earliest_exchange_start, time) -> None:
    candles = [
        Candle(time=12),
        Candle(time=14),
        Candle(time=16),
        Candle(time=18),
    ]
    exchange = fakes.Exchange()
    exchange.can_stream_historical_earliest_candle = False
    historian = Historian(
        chandler=fakes.Chandler(candles={('exchange', 'eth-btc', 2): candles}),  # type: ignore
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start
    )

    first_candle = await historian.find_first_candle('exchange', 'eth-btc', 2)

    assert first_candle.time == 12


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (1, 2),  # No candles
    (0, 1),  # Single last candle.
])
async def test_find_first_candle_not_found(storage, earliest_exchange_start, time) -> None:
    exchange = fakes.Exchange()
    exchange.can_stream_historical_earliest_candle = False
    historian = Historian(
        chandler=fakes.Chandler(
            candles={('exchange', 'eth-btc', 1): [Candle(time=0)]}
        ),  # type: ignore
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start
    )

    with pytest.raises(ValueError):
        await historian.find_first_candle('exchange', 'eth-btc', 1)


async def test_resource_caching_to_storage(storage) -> None:
    exchange = fakes.Exchange(historical_candles=[Candle()])

    historian = Historian(fakes.Chandler(), storage, [exchange], earliest_exchange_start=0)
    await historian.find_first_candle('exchange', 'eth-btc', 1)

    assert len(storage.get_calls) == 1
    assert len(storage.set_calls) == 1

    await historian.find_first_candle('exchange', 'eth-btc', 1)

    assert len(storage.get_calls) == 2
    assert len(storage.set_calls) == 1

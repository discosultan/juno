import pytest

from juno.candles import Candle, exchanges
from juno.exchanges import Binance, Coinbase, Exchange, Kraken
from juno.time import HOUR_MS, MIN_MS, strptimestamp
from juno.typing import types_match
from tests.exchanges import parametrize_exchange, skip_not_configured


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase])  # TODO: Add gateio.
async def test_stream_historical_candles(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    start = strptimestamp('2018-01-01')
    exchange = exchange_session.to_exchange(exchanges.Exchange, exchanges)  # type: ignore

    count = 0
    async for candle in exchange.stream_historical_candles(
        symbol='eth-btc', interval=HOUR_MS, start=start, end=start + HOUR_MS
    ):
        if count == 1:
            pytest.fail('Expected a single candle')
        count += 1

        assert types_match(candle, Candle)
        assert candle.time == start


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Kraken])  # TODO: Add gateio.
async def test_connect_stream_candles(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    exchange = exchange_session.to_exchange(exchanges.Exchange, exchanges)  # type: ignore

    async with exchange.connect_stream_candles(symbol='eth-btc', interval=MIN_MS) as stream:
        async for candle in stream:
            assert types_match(candle, Candle)
            break

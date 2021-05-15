import aiohttp
import pytest

from juno.exchanges import Binance, Coinbase, Exchange, Kraken
from juno.time import HOUR_MS, MIN_MS, strptimestamp, time_ms
from juno.trades import Trade, exchanges
from juno.typing import types_match
from tests.exchanges import parametrize_exchange, skip_not_configured


@pytest.fixture(scope='session')
def loop():
    with aiohttp.test_utils.loop_context() as loop:
        yield loop


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio
async def test_stream_historical_trades(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    # Coinbase can only stream from most recent, hence we use current time.
    if isinstance(exchange_session, Coinbase):
        end = time_ms()
        start = end - 5 * MIN_MS
    else:
        start = strptimestamp('2018-01-01')
        end = start + HOUR_MS
    exchange = exchanges.Exchange.from_session(exchange_session)

    stream = exchange.stream_historical_trades(symbol='eth-btc', start=start, end=end)
    async for trade in stream:
        assert types_match(trade, Trade)
        assert trade.time >= start
        break


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio
async def test_connect_stream_trades(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    # FIAT pairs seem to be more active where supported.
    symbol = 'eth-btc' if isinstance(exchange_session, Binance) else 'eth-eur'
    exchange = exchanges.Exchange.from_session(exchange_session)

    async with exchange.connect_stream_trades(symbol=symbol) as stream:
        async for trade in stream:
            assert types_match(trade, Trade)
            break

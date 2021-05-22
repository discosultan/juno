from decimal import Decimal

import pytest

from juno.assets import ExchangeInfo, Ticker, exchanges
from juno.exchanges import Binance, Coinbase, Exchange, GateIO, Kraken
from juno.typing import types_match
from tests.exchanges import parametrize_exchange, skip_not_configured


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, GateIO, Kraken])
async def test_get_exchange_info(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    exchange = exchange_session.to_exchange(exchanges.Exchange, exchanges)  # type: ignore

    info = await exchange.get_exchange_info()

    assert len(info.assets) > 0
    if '__all__' not in info.assets:
        assert info.assets['btc']

    assert len(info.fees) > 0
    first_fees = next(iter(info.fees.values()))
    assert 0 <= first_fees.taker <= Decimal('0.1')
    assert 0 <= first_fees.maker <= Decimal('0.1')
    assert -4 <= first_fees.taker.as_tuple().exponent <= -1
    assert -4 <= first_fees.maker.as_tuple().exponent <= -1
    if '__all__' not in info.fees:
        assert info.fees['eth-btc']

    assert len(info.filters) > 0
    if '__all__' not in info.filters:
        assert info.filters['eth-btc']

    assert types_match(info, ExchangeInfo)


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance])  # TODO: Add gateio?
async def test_map_tickers(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    exchange = exchange_session.to_exchange(exchanges.Exchange, exchanges)  # type: ignore

    # Note, this is an expensive call!
    tickers = await exchange.map_tickers()

    assert len(tickers) > 0
    assert types_match(tickers, dict[str, Ticker])


@pytest.mark.exchange
@pytest.mark.manual
@parametrize_exchange([Binance, Coinbase, Kraken])  # TODO: Add gateio?
async def test_map_one_ticker(loop, request, exchange_session: Exchange) -> None:
    skip_not_configured(request, exchange_session)

    exchange = exchange_session.to_exchange(exchanges.Exchange, exchanges)  # type: ignore

    tickers = await exchange.map_tickers(symbols=['eth-btc'])

    assert len(tickers) == 1
    assert types_match(tickers, dict[str, Ticker])

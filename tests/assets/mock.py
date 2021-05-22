from unittest.mock import MagicMock

from juno.assets import Exchange, ExchangeInfo, Ticker


def mock_exchange_assets(
    can_list_all_tickers: bool = True,
    exchange_info: ExchangeInfo = ExchangeInfo(),
    tickers: dict[str, Ticker] = {},
) -> MagicMock:
    exchange = MagicMock(spec=Exchange)
    exchange.can_list_all_tickers = can_list_all_tickers
    exchange.get_exchange_info.return_value = exchange_info
    exchange.map_tickers.return_value = tickers
    return exchange

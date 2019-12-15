import asyncio
import csv
import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, cast

from juno import Candle
from juno.agents import Agent, Backtest
from juno.asyncio import list_async
from juno.math import ceil_multiple, floor_multiple
from juno.time import DAY_MS, datetime_utcfromtimestamp_ms
from juno.utils import unpack_symbol

_log = logging.getLogger(__name__)


@asynccontextmanager
async def activate(agent: Agent, plugin_config: Dict[str, Any]) -> AsyncIterator[None]:
    if not isinstance(agent, Backtest):
        raise NotImplementedError()

    @agent.on('finished')
    async def on_finished() -> None:
        backtest = cast(Backtest, agent)
        config = backtest.config
        await asyncio.gather(
            stream_and_export_daily_candles_as_csv(
                backtest, 'coinbase', 'btc-eur'
            ),
            stream_and_export_daily_candles_as_csv(
                backtest, config['exchange'], config['symbol']
            ),
            asyncio.get_running_loop().run_in_executor(
                None, export_trading_summary_as_csv, backtest
            ),
        )

    _log.info('activated')
    yield


async def stream_and_export_daily_candles_as_csv(
    agent: Backtest, exchange: str, symbol: str
) -> None:
    candles = await list_async(agent.chandler.stream_candles(
        exchange,
        symbol,
        DAY_MS,
        floor_multiple(agent.result.start, DAY_MS),
        ceil_multiple(agent.result.end, DAY_MS)
    ))
    await asyncio.get_running_loop().run_in_executor(
        None, export_daily_candles_as_csv, symbol, candles
    )


def export_daily_candles_as_csv(symbol: str, candles: List[Candle]) -> None:
    with open(f'{symbol}-max.csv', 'w', newline='') as csvfile:
        fieldnames = ['snapped_at', 'price', 'market_cap', 'total_volume']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for candle in candles:
            writer.writerow(candle_row(candle))


def candle_row(candle: Candle) -> Dict[str, Any]:
    return {
        'snapped_at': datetime_utcfromtimestamp_ms(candle.time).strftime(r'%Y-%m-%d 00:00:00 UTC'),
        'price': str(candle.close),
        'market_cap': '0.0',
        'total_volume': '0.0'
    }


def export_trading_summary_as_csv(agent: Backtest) -> None:
    config = agent.config
    summary = agent.result

    symbol = config['symbol']
    base_asset, quote_asset = unpack_symbol(symbol)

    with open('tradesheet.csv', 'w', newline='') as csvfile:
        fieldnames = ['Date', 'Buy', 'Sell', 'Units', 'Value Per Unit']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        EUR = Decimal('3347.23')

        writer.writeheader()
        writer.writerow(
            trade_row(summary.start, 'EUR', '', summary.quote * EUR, Decimal('1.0'))
        )
        writer.writerow(
            trade_row(summary.start, quote_asset, 'EUR', summary.quote, Decimal('3347.23'))
        )
        for pos in summary.positions:
            size = pos.fills.total_size - pos.fills.total_fee
            price = pos.fills.total_quote / size
            writer.writerow(trade_row(pos.time, base_asset, quote_asset, size, price))
            size = pos.gain
            price = (pos.fills.total_size - pos.fills.total_fee) / pos.gain
            writer.writerow(trade_row(pos.closing_time, quote_asset, base_asset, size, price))


def trade_row(
    time: int, buy_asset: str, sell_asset: str, buy_size: Decimal, buy_price: Decimal
) -> Dict[str, Any]:
    return {
        'Date': datetime_utcfromtimestamp_ms(time).strftime(r'%m/%d/%Y'),
        'Buy': buy_asset.upper(),
        'Sell': sell_asset.upper(),
        'Units': str(buy_size),
        'Value Per Unit': str(buy_price),
    }

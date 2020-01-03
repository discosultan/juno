import asyncio
import csv
import logging
from decimal import Decimal
from typing import Any, Dict, List

from juno import Candle, Fill, Filters
from juno.asyncio import list_async
from juno.components import Chandler, Informant, Trades
from juno.config import config_from_env, init_instance
from juno.exchanges import Binance, Coinbase
from juno.math import ceil_multiple, floor_multiple
from juno.storages import SQLite
from juno.strategies import MA, MAMACX
from juno.time import DAY_MS, HOUR_MS, datetime_utcfromtimestamp_ms, strptimestamp
from juno.trading import MissedCandlePolicy, Trader, TradingSummary
from juno.utils import unpack_symbol

SYMBOL = 'eth-btc'
INTERVAL = HOUR_MS


async def main() -> None:
    sqlite = SQLite()
    config = config_from_env()
    binance = init_instance(Binance, config)
    coinbase = init_instance(Coinbase, config)
    trades = Trades(sqlite, [binance, coinbase])
    chandler = Chandler(trades, sqlite, [binance, coinbase])
    informant = Informant(sqlite, [binance, coinbase])
    start = floor_multiple(strptimestamp('2019-01-01'), INTERVAL)
    end = floor_multiple(strptimestamp('2019-12-01'), INTERVAL)
    async with binance, coinbase, informant:
        trader = Trader(
            chandler=chandler,
            informant=informant,
            exchange='binance',
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start,
            end=end,
            quote=Decimal('1.0'),
            new_strategy=lambda: MAMACX(3, 73, Decimal('-0.102'), Decimal('0.239'), 4, MA.SMA,
                                        MA.SMMA),
            trailing_stop=Decimal('0.0827'),
            missed_candle_policy=MissedCandlePolicy.LAST
        )
        await trader.run()

        _, filters = informant.get_fees_filters('binance', SYMBOL)

        await asyncio.gather(
            stream_and_export_daily_candles_as_csv(
                chandler, trader.summary, 'coinbase', 'btc-eur'
            ),
            stream_and_export_daily_candles_as_csv(
                chandler, trader.summary, 'coinbase', 'eth-eur'
            ),
            asyncio.get_running_loop().run_in_executor(
                None, export_trading_summary_as_csv, filters, trader.summary, SYMBOL
            ),
        )

    logging.info('done')


async def stream_and_export_daily_candles_as_csv(
    chandler: Chandler, summary: TradingSummary, exchange: str, symbol: str
) -> None:
    candles = await list_async(chandler.stream_candles(
        exchange,
        symbol,
        DAY_MS,
        floor_multiple(summary.start, DAY_MS),
        ceil_multiple(summary.end, DAY_MS)
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


def export_trading_summary_as_csv(filters: Filters, summary: TradingSummary, symbol: str) -> None:
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
            assert pos.closing_fills

            buy_size = Fill.total_size(pos.fills) - Fill.total_fee(pos.fills)
            buy_price = filters.price.round_down(Fill.total_quote(pos.fills) / buy_size)
            writer.writerow(trade_row(pos.time, base_asset, quote_asset, buy_size, buy_price))

            sell_size = pos.gain
            sell_price = filters.price.round_down(buy_size / sell_size)
            writer.writerow(
                trade_row(pos.closing_time, quote_asset, base_asset, sell_size, sell_price)
            )


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


asyncio.run(main())

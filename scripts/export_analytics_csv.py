import asyncio
import csv
from decimal import Decimal
from typing import Any

from juno import Candle, Filters, Interval_, Symbol, Symbol_, Timestamp_, stop_loss, strategies
from juno.components import Chandler, Informant, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Coinbase
from juno.inspect import GenericConstructor
from juno.math import ceil_multiple, floor_multiple
from juno.storages import SQLite
from juno.traders import Basic, BasicConfig
from juno.trading import TradingSummary

SYMBOL = "eth-btc"
INTERVAL = Interval_.HOUR


async def main() -> None:
    sqlite = SQLite()
    config = from_env()
    binance = init_instance(Binance, config)
    coinbase = init_instance(Coinbase, config)
    exchanges = [binance, coinbase]
    trades = Trades(sqlite, [binance, coinbase])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=exchanges)
    informant = Informant(sqlite, exchanges)
    trader = Basic(chandler=chandler, informant=informant)
    start = floor_multiple(Timestamp_.parse("2019-01-01"), INTERVAL)
    end = floor_multiple(Timestamp_.parse("2019-12-01"), INTERVAL)
    async with binance, coinbase, informant, trades, chandler:
        trader_config = BasicConfig(
            exchange="binance",
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start,
            end=end,
            quote=Decimal("1.0"),
            strategy=GenericConstructor.from_type(
                strategies.DoubleMA2,
                **{
                    "short_period": 3,
                    "long_period": 73,
                    "neg_threshold": Decimal("-0.102"),
                    "pos_threshold": Decimal("0.239"),
                    "short_ma": "sma",
                    "long_ma": "smma",
                },
            ),
            stop_loss=GenericConstructor.from_type(stop_loss.Basic, Decimal("0.0827")),
        )
        trader_state = await trader.initialize(trader_config)

        trading_summary = await trader.run(trader_state)

        _, filters = informant.get_fees_filters("binance", SYMBOL)

        await asyncio.gather(
            stream_and_export_daily_candles_as_csv(
                chandler, trading_summary, "coinbase", "btc-eur"
            ),
            stream_and_export_daily_candles_as_csv(
                chandler, trading_summary, "coinbase", "eth-eur"
            ),
            asyncio.get_running_loop().run_in_executor(
                None, export_trading_summary_as_csv, filters, trading_summary, SYMBOL
            ),
        )


async def stream_and_export_daily_candles_as_csv(
    chandler: Chandler, summary: TradingSummary, exchange: str, symbol: Symbol
) -> None:
    assert summary.end
    candles = await chandler.list_candles(
        exchange,
        symbol,
        Interval_.DAY,
        floor_multiple(summary.start, Interval_.DAY),
        ceil_multiple(summary.end, Interval_.DAY),
    )
    await asyncio.get_running_loop().run_in_executor(
        None, export_daily_candles_as_csv, symbol, candles
    )


def export_daily_candles_as_csv(symbol: Symbol, candles: list[Candle]) -> None:
    with open(f"{symbol}-max.csv", "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["snapped_at", "price", "market_cap", "total_volume"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for candle in candles:
            writer.writerow(candle_row(candle))


def candle_row(candle: Candle) -> dict[str, Any]:
    return {
        "snapped_at": Timestamp_.to_datetime_utc(candle.time).strftime(r"%Y-%m-%d 00:00:00 UTC"),
        "price": str(candle.close),
        "market_cap": "0.0",
        "total_volume": "0.0",
    }


def export_trading_summary_as_csv(
    filters: Filters, summary: TradingSummary, symbol: Symbol
) -> None:
    base_asset, quote_asset = Symbol_.assets(symbol)
    quote = summary.starting_assets[quote_asset]

    with open("tradesheet.csv", "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["Date", "Buy", "Sell", "Units", "Value Per Unit"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        EUR = Decimal("3347.23")

        writer.writeheader()
        writer.writerow(trade_row(summary.start, "EUR", "", quote * EUR, Decimal("1.0")))
        writer.writerow(trade_row(summary.start, quote_asset, "EUR", quote, Decimal("3347.23")))
        for pos in summary.positions:
            buy_size = pos.base_gain
            buy_price = filters.price.round_down(pos.cost / buy_size)
            writer.writerow(trade_row(pos.open_time, base_asset, quote_asset, buy_size, buy_price))

            sell_size = pos.gain
            sell_price = filters.price.round_down(buy_size / sell_size)
            writer.writerow(
                trade_row(pos.close_time, quote_asset, base_asset, sell_size, sell_price)
            )


def trade_row(
    time: int, buy_asset: str, sell_asset: str, buy_size: Decimal, buy_price: Decimal
) -> dict[str, Any]:
    return {
        "Date": Timestamp_.to_datetime_utc(time).strftime(r"%m/%d/%Y"),
        "Buy": buy_asset.upper(),
        "Sell": sell_asset.upper(),
        "Units": str(buy_size),
        "Value Per Unit": str(buy_price),
    }


asyncio.run(main())

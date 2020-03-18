import asyncio
import logging
from decimal import Decimal
from typing import Any

from juno import Fill
from juno.agents import Agent, AgentStatus
from juno.storages import SQLite
from juno.strategies import MAMACX
from juno.trading import Position, Trader, TradingSummary
from juno.utils import format_as_config


async def main() -> None:
    trading_summary = TradingSummary(
        start=1582311900000,
        quote=Decimal('0.02'),
    )
    trading_summary._positions = [
        Position(
            symbol='ada-btc',
            open_time=1582683600000,
            open_fills=[
                Fill(
                    price=Decimal('5.75187032921e-06'),
                    size=Decimal('3474.52200000'),
                    fee=Decimal('0.0'),
                    fee_asset='ada',
                ),
            ],
            close_time=1582700400000,
            close_fills=[
                Fill(
                    price=Decimal('5.72426885435e-06'),
                    size=Decimal('3474.00000000'),
                    fee=Decimal('0.0'),
                    fee_asset='btc',
                ),
            ],
        ),
        Position(
            symbol='ada-btc',
            open_time=1582766400000,
            open_fills=[
                Fill(
                    price=Decimal('5.4954954955e-06'),
                    size=Decimal('3618.37800000'),
                    fee=Decimal('0.0'),
                    fee_asset='ada',
                ),
            ],
            close_time=1582782900000,
            close_fills=[
                Fill(
                    price=Decimal('5.67432006633e-06'),
                    size=Decimal('3618.00000000'),
                    fee=Decimal('0.0000134999999901533800000'),
                    fee_asset='btc',
                ),
            ],
        ),
    ]
    trader_state: Trader.State[Any] = Trader.State(
        strategy=MAMACX(84, 92, Decimal('-0.172'), Decimal('0.377'), 0, 'sma', 'ema2'),
        quote=Decimal('0.0205325200000000'),
        summary=trading_summary,
    )
    agent_state = Agent.State(
        name='ada-btc-2020-02-20',
        status=AgentStatus.ERRORED,
        result=trader_state,
    )
    sqlite = SQLite()
    await sqlite.set(
        'default',
        f'live_{agent_state.name}_state',
        agent_state,
    )
    logging.info(format_as_config(trading_summary))
    assert trading_summary.profit == Decimal('0.0005325200000000')


asyncio.run(main())
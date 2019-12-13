import asyncio
import csv
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from juno.agents import Agent, Backtest
from juno.time import datetime_utcfromtimestamp_ms
from juno.trading import TradingSummary
from juno.utils import unpack_symbol

_log = logging.getLogger(__name__)


@asynccontextmanager
async def activate(agent: Agent, plugin_config: Dict[str, Any]) -> AsyncIterator[None]:
    if not isinstance(agent, Backtest):
        raise NotImplementedError()

    @agent.on('finished')
    async def on_finished() -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, export_trading_summary_as_csv, agent.config, agent.result
        )

    _log.info('activated')
    yield


def export_trading_summary_as_csv(config: Dict[str, Any], summary: TradingSummary) -> None:
    _, quote_asset = unpack_symbol(config['symbol'])

    with open('foo.csv', 'w', newline='') as csvfile:
        fieldnames = ['Date', 'Buy', 'Sell', 'Units', 'Value Per Unit']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerow(create_row(summary.start, quote_asset, '', summary.quote))
        for pos in summary.positions:
            pass


def create_row(time, base_asset, quote_asset, size):
    return {
        'Date': datetime_utcfromtimestamp_ms(time).strftime(r'%m/%d/%Y'),
        'Buy': quote_asset.upper(),
        'Sell': base_asset.upper(),
        'Value Per Unit': str(size),
    }

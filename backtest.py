import asyncio
import logging

from juno.engine import Engine


_log = logging.getLogger(__name__)


class BacktestEngine(Engine):

    async def run(self):
        _log.info('running backtest')


try:
    asyncio.run(BacktestEngine().main())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')

import asyncio
import logging

from juno.engine import Engine


_log = logging.getLogger(__name__)


class BacktestEngine(Engine):

    async def run(self):
        _log.info('go fuck yourself')


engine = BacktestEngine()
asyncio.run(engine.main())

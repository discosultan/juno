import asyncio
import logging

from juno.engine import Engine


_log = logging.getLogger(__name__)

_default_settings = {
    'exchange'
}


class BacktestEngine(Engine):

    async def run(self):
        _log.info('running backtest')
        informant = self.components['informant']
        settings = _default_settings.update(self.config.get('backtest') or {})

        async def trade():

            async for candle, primary in exchange.stream_candles()


# class TradingSummary:



try:
    asyncio.run(BacktestEngine().main())
except KeyboardInterrupt:
    _log.info('program interrupted by keyboard')

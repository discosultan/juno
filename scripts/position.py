from __future__ import annotations

import argparse
import asyncio
import logging
from decimal import Decimal
from typing import Dict

from juno.brokers import Broker, Limit
from juno.components import Chandler, Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Exchange
from juno.storages import SQLite
from juno.trading import CloseReason, PositionMixin, TradingMode
from juno.typing import ExcType, ExcValue, Traceback

parser = argparse.ArgumentParser()
parser.add_argument('symbols', type=lambda s: s.split(','))
parser.add_argument('quote', type=Decimal)
parser.add_argument(
    '-s', '--short',
    action='store_true',
    default=False,
    help='if set, open short; otherwise long position',
)
parser.add_argument('--cycles', type=int, default=1)
args = parser.parse_args()


class PositionHandler(PositionMixin):
    async def __aenter__(self) -> PositionHandler:
        exchange = init_instance(Binance, from_env())
        self._exchanges = {'binance': exchange}
        storage = SQLite()
        self._informant = Informant(storage=storage, exchanges=[exchange])
        self._chandler = Chandler(storage=storage, exchanges=[exchange])
        self._wallet = Wallet(exchanges=[exchange])
        self._orderbook = Orderbook(exchanges=[exchange])
        self._broker = Limit(informant=self._informant, orderbook=self._orderbook)
        await asyncio.gather(*(e.__aenter__() for e in self._exchanges.values()))
        await self._wallet.__aenter__()
        await asyncio.gather(
            self._informant.__aenter__(),
            self._orderbook.__aenter__(),
        )
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await asyncio.gather(
            self._informant.__aexit__(exc_type, exc, tb),
            self._orderbook.__aexit__(exc_type, exc, tb),
        )
        await self._wallet.__aexit__(exc_type, exc, tb)
        await asyncio.gather(*(e.__aexit__(exc_type, exc, tb) for e in self._exchanges.values()))

    @property
    def informant(self) -> Informant:
        return self._informant

    @property
    def chandler(self) -> Chandler:
        return self._chandler

    @property
    def broker(self) -> Broker:
        return self._broker

    @property
    def exchanges(self) -> Dict[str, Exchange]:
        return self._exchanges

    @property
    def wallet(self) -> Wallet:
        return self._wallet


async def main() -> None:
    async with PositionHandler() as handler:
        for i in range(args.cycles):
            logging.info(f'cycle {i}')

            if args.short:
                logging.info(f'opening short position(s) for {args.symbols}')
                positions = await asyncio.gather(
                    *(handler.open_short_position(
                        exchange='binance', symbol=s, collateral=args.quote, mode=TradingMode.LIVE
                    ) for s in args.symbols)
                )

                logging.info(f'closing short position(s) for {args.symbols}')
                await asyncio.gather(
                    *(handler.close_short_position(
                        position=p, mode=TradingMode.LIVE, reason=CloseReason.STRATEGY
                    ) for p in positions)
                )
            else:
                logging.info(f'opening long position(s) for {args.symbols}')
                positions = await asyncio.gather(
                    *(handler.open_long_position(
                        exchange='binance', symbol=s, quote=args.quote, mode=TradingMode.LIVE
                    ) for s in args.symbols)
                )

                logging.info(f'closing long position(s) for {args.symbols}')
                await asyncio.gather(
                    *(handler.close_long_position(
                        position=p, mode=TradingMode.LIVE, reason=CloseReason.STRATEGY
                    ) for p in positions)
                )


asyncio.run(main())

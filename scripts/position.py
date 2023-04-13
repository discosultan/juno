from __future__ import annotations

import argparse
import asyncio
import logging
import os
from decimal import Decimal

from juno.brokers import Broker, Limit, Market
from juno.common import Balance
from juno.components import Chandler, Informant, Orderbook, Trades, User
from juno.custodians import Savings, Spot, Stub
from juno.exchanges import Exchange
from juno.positioner import Positioner
from juno.primitives.symbol import Symbol_
from juno.storages import SQLite
from juno.trading import CloseReason, TradingMode

parser = argparse.ArgumentParser()
parser.add_argument("symbols", type=lambda s: s.split(","))
parser.add_argument("-e", "--exchange", default=os.environ.get("JUNO__EXCHANGE", "binance"))
parser.add_argument("-q", "--quote", type=Decimal, default=None)
parser.add_argument(
    "-s",
    "--short",
    action="store_true",
    default=False,
    help="if set, open short; otherwise long positions",
)
parser.add_argument("--cycles", type=int, default=1)
parser.add_argument("--custodian", default="spot", help="either savings, spot or stub")
parser.add_argument(
    "--sleep", type=float, default=0.0, help="seconds to sleep before closing positions"
)
parser.add_argument(
    "-b",
    "--broker",
    default=os.environ.get("JUNO__BROKER", "limit"),
    help="either limit or market",
)
parser.add_argument(
    "--use-edit-order-if-possible",
    action="store_true",
    default=True,
    help="if set, the broker will try to use edit order instead of cancel order + place order",
)
args = parser.parse_args()


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    storage = SQLite()
    informant = Informant(storage=storage, exchanges=[exchange])
    trades = Trades(storage=storage, exchanges=[exchange])
    chandler = Chandler(storage=storage, exchanges=[exchange], trades=trades)
    user = User(exchanges=[exchange])
    orderbook = Orderbook(exchanges=[exchange])
    broker: Broker
    if args.broker == "limit":
        broker = Limit(
            informant=informant,
            orderbook=orderbook,
            user=user,
            use_edit_order_if_possible=args.use_edit_order_if_possible,
        )
    elif args.broker == "market":
        broker = Market(informant=informant, orderbook=orderbook, user=user)
    else:
        raise ValueError(f"Unknown broker {args.broker}")
    positioner = Positioner(
        informant=informant,
        chandler=chandler,
        orderbook=orderbook,
        broker=broker,
        user=user,
        custodians=[Savings(user), Spot(user), Stub()],
        exchanges=[exchange],
    )

    async with exchange, informant, chandler, user, orderbook:
        quote_assets = {Symbol_.quote_asset(s) for s in args.symbols}
        if args.quote:
            quotes = {asset: args.quote for asset in quote_assets}
        else:
            balances = (await user.map_balances(exchange=args.exchange, accounts=["spot"]))["spot"]
            quotes = {
                asset: balances.get(asset, Balance.zero()).available for asset in quote_assets
            }
        logging.info(quotes)

        for i in range(args.cycles):
            logging.info(f"cycle {i}")

            logging.info(
                f"opening {'short' if args.short else 'long'} position(s) for {args.symbols}"
            )
            positions = await positioner.open_positions(
                exchange=args.exchange,
                custodian=args.custodian,
                mode=TradingMode.LIVE,
                entries=[(s, quotes[Symbol_.quote_asset(s)], args.short) for s in args.symbols],
            )

            if args.sleep > 0:
                logging.info(f"sleeping for {args.sleep} seconds")
                await asyncio.sleep(args.sleep)

            logging.info(
                f"closing {'short' if args.short else 'long'} position(s) for {args.symbols}"
            )
            closed_positions = await positioner.close_positions(
                custodian=args.custodian,
                mode=TradingMode.LIVE,
                entries=[(p, CloseReason.STRATEGY) for p in positions],
            )

            for closed_position in closed_positions:
                quotes[Symbol_.quote_asset(closed_position.symbol)] += closed_position.profit

            logging.info(quotes)


asyncio.run(main())

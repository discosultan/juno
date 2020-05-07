import abc
import logging
from decimal import Decimal
from typing import Dict

from juno import Candle, Fill, Filters, OrderException
from juno.brokers import Broker
from juno.components import Informant
from juno.exchanges import Exchange
from juno.math import ceil_multiple, round_down, round_half_up
from juno.time import HOUR_MS
from juno.utils import unpack_symbol

from .common import Position

_log = logging.getLogger(__name__)


class SimulatedPositionMixin(abc.ABC):
    @abc.abstractproperty
    def informant(self) -> Informant:
        pass

    def open_simulated_long_position(
        self, candle: Candle, exchange: str, symbol: str, quote: Decimal
    ) -> Position.OpenLong:
        price = candle.close
        base_asset, _ = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)

        size = filters.size.round_down(quote / price)
        if size == 0:
            raise OrderException()
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(size * fees.taker, filters.base_precision)

        return Position.OpenLong(
            symbol=symbol,
            time=candle.time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
            )],
        )

    # TODO: Take exchange and symbol from position?
    def close_simulated_long_position(
        self, candle: Candle, position: Position.OpenLong, exchange: str, symbol: str
    ) -> Position.Long:
        price = candle.close
        _, quote_asset = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)

        size = filters.size.round_down(position.base_gain)
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        return position.close(
            time=candle.time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=quote_asset
            )],
        )

    def open_simulated_short_position(
        self, candle: Candle, exchange: str, symbol: str, collateral: Decimal
    ) -> Position.OpenShort:
        price = candle.close
        _, quote_asset = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)
        margin_multiplier = self.informant.get_margin_multiplier(exchange)

        borrowed = _calculate_borrowed(filters, margin_multiplier, collateral, price)
        quote = round_down(price * borrowed, filters.quote_precision)
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        return Position.OpenShort(
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=candle.time,
            fills=[Fill(
                price=price, size=borrowed, quote=quote, fee=fee, fee_asset=quote_asset
            )],
        )

    def close_simulated_short_position(
        self, candle: Candle, position: Position.OpenShort, exchange: str, symbol: str
    ) -> Position.Short:
        price = candle.close
        base_asset, _ = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)
        borrow_info = self.informant.get_borrow_info(exchange, base_asset)

        interest = _calculate_interest(
            borrowed=position.borrowed,
            hourly_rate=borrow_info.hourly_interest_rate,
            start=position.time,
            end=candle.time,
        )
        size = position.borrowed + interest
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(size * fees.taker, filters.base_precision)
        size += fee

        return position.close(
            time=candle.time,
            interest=interest,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
            )],
        )


class PositionMixin(abc.ABC):
    @abc.abstractproperty
    def informant(self) -> Informant:
        pass

    @abc.abstractproperty
    def broker(self) -> Broker:
        pass

    @abc.abstractproperty
    def exchanges(self) -> Dict[str, Exchange]:
        pass

    async def open_long_position(
        self, candle: Candle, exchange: str, symbol: str, quote: Decimal, test: bool
    ) -> Position.OpenLong:
        res = await self.broker.buy_by_quote(
            exchange=exchange,
            symbol=symbol,
            quote=quote,
            test=test,
        )

        return Position.OpenLong(
            symbol=symbol,
            time=candle.time,
            fills=res.fills,
        )

    async def close_long_position(
        self, candle: Candle, position: Position.OpenLong, exchange: str, symbol: str, test: bool
    ) -> Position.Long:
        res = await self.broker.sell(
            exchange=exchange,
            symbol=symbol,
            size=position.base_gain,
            test=test,
        )

        return position.close(
            time=candle.time,
            fills=res.fills,
        )

    async def open_short_position(
        self, candle: Candle, exchange: str, symbol: str, collateral: Decimal, test: bool
    ) -> Position.OpenShort:
        price = candle.close
        base_asset, quote_asset = unpack_symbol(symbol)
        _, filters = self.informant.get_fees_filters(exchange, symbol)
        margin_multipler = self.informant.get_margin_multiplier(exchange)
        exchange_instance = self.exchanges[exchange]

        if test:
            borrowed = _calculate_borrowed(filters, margin_multipler, collateral, price)
        else:
            _log.info(f'transferring {collateral} {quote_asset} to margin account')
            await exchange_instance.transfer(quote_asset, collateral, margin=True)
            borrowed = await exchange_instance.get_max_borrowable(quote_asset)
            _log.info(f'borrowing {borrowed} {base_asset} from exchange')
            await exchange_instance.borrow(asset=base_asset, size=borrowed)

        res = await self.broker.sell(
            exchange=exchange,
            symbol=symbol,
            size=borrowed,
            test=test,
            margin=not test,
        )

        return Position.OpenShort(
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=candle.time,
            fills=res.fills,
        )

    async def close_short_position(
        self, candle: Candle, position: Position.OpenShort, exchange: str, symbol: str, test: bool
    ) -> Position.Short:
        base_asset, quote_asset = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)
        borrow_info = self.informant.get_borrow_info(exchange, base_asset)
        exchange_instance = self.exchanges[exchange]

        interest = (
            _calculate_interest(
                borrowed=position.borrowed,
                hourly_rate=borrow_info.hourly_interest_rate,
                start=position.time,
                end=candle.time,
            ) if test
            else (await exchange_instance.map_balances(margin=True))[base_asset].interest
        )
        size = position.borrowed + interest
        fee = round_half_up(size * fees.taker, filters.base_precision)
        size = filters.size.round_up(size + fee)
        res = await self.broker.buy(
            exchange=exchange,
            symbol=symbol,
            size=size,
            test=test,
            margin=not test,
        )
        closed_position = position.close(
            interest=interest,
            time=candle.time,
            fills=res.fills,
        )
        if not test:
            _log.info(
                f'repaying {position.borrowed} + {interest} {base_asset} to exchange'
            )
            await exchange_instance.repay(base_asset, position.borrowed + interest)
            # Validate!
            # TODO: Remove if known to work or pay extra if needed.
            new_balance = (await exchange_instance.map_balances(margin=True))[base_asset]
            if new_balance.repay != 0:
                _log.error(f'did not repay enough; balance {new_balance}')
                assert new_balance.repay == 0

            transfer = closed_position.collateral + closed_position.profit
            _log.info(f'transferring {transfer} {quote_asset} to spot account')
            await exchange_instance.transfer(quote_asset, transfer, margin=False)

        return closed_position


def _calculate_borrowed(
    filters: Filters, margin_multiplier: int, collateral: Decimal, price: Decimal
) -> Decimal:
    collateral_size = filters.size.round_down(collateral / price)
    if collateral_size == 0:
        raise OrderException('Collateral base size 0')
    borrowed = collateral_size * (margin_multiplier - 1)
    if borrowed == 0:
        raise OrderException('Borrowed 0; incorrect margin multiplier?')
    return borrowed


def _calculate_interest(borrowed: Decimal, hourly_rate: Decimal, start: int, end: int) -> Decimal:
    duration = ceil_multiple(end - start, HOUR_MS) // HOUR_MS
    return borrowed * duration * hourly_rate

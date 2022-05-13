import asyncio
import logging
from collections import defaultdict
from decimal import Decimal

from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from juno import BadOrder, Balance, Fill, Filters, Timestamp
from juno.brokers import Broker
from juno.components import Chandler, Informant, User
from juno.custodians import Custodian
from juno.math import ceil_multiple, round_down, round_half_up
from juno.time import HOUR_MS, MIN_MS, strftimestamp, time_ms
from juno.trading import CloseReason, Position, TradingMode
from juno.utils import extract_public, unpack_assets, unpack_base_asset, unpack_quote_asset

_log = logging.getLogger(__name__)


class _UnexpectedExchangeResult(Exception):
    pass


class Positioner:
    def __init__(
        self,
        informant: Informant,
        chandler: Chandler,
        broker: Broker,
        user: User,
        custodians: list[Custodian],
    ) -> None:
        self._informant = informant
        self._chandler = chandler
        self._broker = broker
        self._user = user
        self._custodians = {type(c).__name__.lower(): c for c in custodians}

    async def open_positions(
        self,
        exchange: str,
        custodian: str,
        mode: TradingMode,
        entries: list[tuple[str, Decimal, bool]],  # [symbol, quote, short]
    ) -> list[Position.Open]:
        if len(entries) == 0:
            return []

        _log.info(f"opening position(s): {entries}")
        custodian_instance = self._custodians[custodian]

        # Acquire funds from custodian.
        acquires: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.0"))
        for symbol, quote, _ in entries:
            quote_asset = unpack_quote_asset(symbol)
            acquires[(exchange, quote_asset)] += quote
        await asyncio.gather(
            *(
                custodian_instance.acquire(exchange, asset, quote)
                for (exchange, asset), quote in acquires.items()
            )
        )

        result = await asyncio.gather(
            *(
                self._open_short_position(exchange, symbol, quote, mode)
                if short
                else self._open_long_position(exchange, symbol, quote, mode)
                for symbol, quote, short in entries
            )
        )

        # Release funds to custodian.
        # ONLY RELEASE FOR OPEN LONG POSITIONS.
        releases: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.0"))
        for pos in (p for p in result if isinstance(p, Position.OpenLong)):
            base_asset = unpack_base_asset(pos.symbol)
            releases[(pos.exchange, base_asset)] += pos.base_gain
        await asyncio.gather(
            *(
                custodian_instance.release(exchange, asset, quote)
                for (exchange, asset), quote in releases.items()
            )
        )

        _log.info(f"opened position(s): {entries}")
        return result

    async def close_positions(
        self,
        custodian: str,
        mode: TradingMode,
        entries: list[tuple[Position.Open, CloseReason]],  # [position, reason]
    ) -> list[Position.Closed]:
        if len(entries) == 0:
            return []

        log_entries = [(p.symbol, r) for p, r in entries]
        _log.info(f"closing position(s): {log_entries}")
        custodian_instance = self._custodians[custodian]

        # Acquire funds from custodian.
        # ONLY ACQUIRE FOR OPEN LONG POSITIONS.
        acquires: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.0"))
        for open_long in (p for p, _ in entries if isinstance(p, Position.OpenLong)):
            base_asset = unpack_base_asset(open_long.symbol)
            acquires[(open_long.exchange, base_asset)] += open_long.base_gain
        await asyncio.gather(
            *(
                custodian_instance.acquire(exchange, asset, quote)
                for (exchange, asset), quote in acquires.items()
            )
        )

        result = await asyncio.gather(
            *(
                self._close_short_position(position, mode, reason)
                if isinstance(position, Position.OpenShort)
                else self._close_long_position(position, mode, reason)
                for position, reason in entries
            )
        )

        # Release funds to custodian.
        releases: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0.0"))
        for position in result:
            quote_asset = unpack_quote_asset(position.symbol)
            releases[(position.exchange, quote_asset)] += position.gain
        await asyncio.gather(
            *(
                custodian_instance.release(exchange, asset, quote)
                for (exchange, asset), quote in releases.items()
            )
        )

        _log.info(f"closed position(s): {log_entries}")
        return result

    async def _open_long_position(
        self, exchange: str, symbol: str, quote: Decimal, mode: TradingMode
    ) -> Position.Open:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f"opening long position {symbol} {mode.name} with {quote} quote")

        res = await self._broker.buy(
            exchange=exchange,
            symbol=symbol,
            quote=quote,
            account="spot",
            test=mode is TradingMode.PAPER,
        )
        open_position = Position.OpenLong(
            exchange=exchange,
            symbol=symbol,
            time=res.time,
            fills=res.fills,
        )

        _log.info(f"opened long position {open_position.symbol} {mode.name}")
        _log.debug(extract_public(open_position))
        return open_position

    async def _close_long_position(
        self, position: Position.OpenLong, mode: TradingMode, reason: CloseReason
    ) -> Position.Closed:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f"closing long position {position.symbol} {mode.name}")

        res = await self._broker.sell(
            exchange=position.exchange,
            symbol=position.symbol,
            size=position.base_gain,
            account="spot",
            test=mode is TradingMode.PAPER,
        )
        closed_position = position.close(
            time=res.time,
            fills=res.fills,
            reason=reason,
        )

        _log.info(f"closed long position {closed_position.symbol} {mode.name}")
        _log.debug(extract_public(closed_position))
        return closed_position

    async def _open_short_position(
        self, exchange: str, symbol: str, collateral: Decimal, mode: TradingMode
    ) -> Position.Open:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f"opening short position {symbol} {mode.name} with {collateral} collateral")

        base_asset, quote_asset = unpack_assets(symbol)
        _, filters = self._informant.get_fees_filters(exchange, symbol)
        # TODO: We could get a maximum margin multiplier from the exchange and use that but use the
        # lowers multiplier for now for reduced risk.
        margin_multiplier = 2
        # margin_multiplier = self.informant.get_margin_multiplier(exchange)

        price = (await self._chandler.get_last_candle(exchange, symbol, MIN_MS)).close

        if mode is TradingMode.PAPER:
            limit = self._informant.get_borrow_info(
                exchange=exchange, asset=base_asset, account=symbol
            ).limit
            borrowed = _calculate_borrowed(filters, margin_multiplier, limit, collateral, price)
        else:
            _log.info(f"transferring {collateral} {quote_asset} from spot to {symbol} account")
            await self._user.transfer(
                exchange=exchange,
                asset=quote_asset,
                size=collateral,
                from_account="spot",
                to_account=symbol,
            )

            # Looks like Binance caches the result, so even with retries, it can be that it will
            # keep returning 0 while we have sufficient collateral present. To circumvent, once
            # we hit the retry limit, we will try one more time. But this time, by first borrowing
            # QUOTE, instead of base asset. This seems to reset the cache.
            try:
                borrowable = await self._get_max_borrowable_with_retries(
                    exchange=exchange, account=symbol, asset=base_asset
                )
            except RetryError:
                _log.warning(
                    "borrowable 0 even after retries; trying once more by first getting quote "
                    "asset max borrowable; hopefully this solves any caching issue on the exchange"
                )
                await self._user.get_max_borrowable(
                    exchange=exchange, account=symbol, asset=quote_asset
                )
                borrowable = await self._get_max_borrowable_with_retries(
                    exchange=exchange, account=symbol, asset=base_asset
                )

            borrowed = _calculate_borrowed(
                filters, margin_multiplier, borrowable, collateral, price
            )
            _log.info(f"borrowing {borrowed} {base_asset} from {exchange}")
            await self._user.borrow(
                exchange=exchange,
                asset=base_asset,
                size=borrowed,
                account=symbol,
            )

        res = await self._broker.sell(
            exchange=exchange,
            symbol=symbol,
            size=borrowed,
            account=symbol if mode is TradingMode.LIVE else "spot",
            test=mode is TradingMode.PAPER,
        )

        open_position = Position.OpenShort(
            exchange=exchange,
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=res.time,
            fills=res.fills,
        )
        _log.info(f"opened short position {open_position.symbol} {mode.name}")
        _log.debug(extract_public(open_position))
        return open_position

    # Even when waiting for wallet update, Binance can still return 0 as borrow amount for base
    # asset. We retry a couple of times as we have nothing else to await on.
    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(_UnexpectedExchangeResult),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def _get_max_borrowable_with_retries(
        self, exchange: str, account: str, asset: str
    ) -> Decimal:
        borrowable = await self._user.get_max_borrowable(
            exchange=exchange, account=account, asset=asset
        )
        if borrowable == 0:
            raise _UnexpectedExchangeResult(
                f"Borrowable amount 0 for account {account} asset {asset}"
            )
        return borrowable

    async def _close_short_position(
        self, position: Position.OpenShort, mode: TradingMode, reason: CloseReason
    ) -> Position.Closed:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f"closing short position {position.symbol} {mode.name}")

        base_asset, quote_asset = unpack_assets(position.symbol)
        asset_info = self._informant.get_asset_info(exchange=position.exchange, asset=base_asset)
        borrow_info = self._informant.get_borrow_info(
            exchange=position.exchange, asset=base_asset, account=position.symbol
        )

        # TODO: Take interest from wallet (if Binance supports streaming it for margin account)
        if mode is TradingMode.PAPER:
            interest = _calculate_interest(
                borrowed=position.borrowed,
                hourly_rate=borrow_info.hourly_interest_rate,
                start=position.time,
                end=time_ms(),
                precision=asset_info.precision,
            )
        else:
            interest = (
                await self._user.get_balance(
                    exchange=position.exchange,
                    account=position.symbol,
                    asset=base_asset,
                )
            ).interest

        # Add an extra interest tick in case it is about to get ticked.
        interest_per_tick = borrow_info.hourly_interest_rate * position.borrowed
        repay = position.borrowed + interest
        size = repay + interest_per_tick

        res = await self._broker.buy(
            exchange=position.exchange,
            symbol=position.symbol,
            size=size,
            account=position.symbol if mode is TradingMode.LIVE else "spot",
            test=mode is TradingMode.PAPER,
            ensure_size=True,
        )
        closed_position = position.close(
            interest=interest,
            time=res.time,
            fills=res.fills,
            reason=reason,
        )
        if mode is TradingMode.LIVE:
            _log.info(
                f"repaying {position.borrowed} + {interest} {base_asset} to {position.exchange}"
            )
            await self._user.repay(
                exchange=position.exchange,
                asset=base_asset,
                size=repay,
                account=position.symbol,
            )

            # It can be that there was an interest tick right before repaying. This means there may
            # still be borrowed funds on the account. Double check and repay more if that is the
            # case.
            # Careful with this check! We may have another position still open.
            new_balance = await self._get_repaid_balance_with_retries(
                exchange=position.exchange,
                account=position.symbol,
                asset=base_asset,
                original_borrowed=position.borrowed,
            )
            if new_balance.repay > 0:
                _log.warning(
                    f"did not repay enough; still {new_balance.repay} {base_asset} to be repaid"
                )
                if new_balance.available >= new_balance.repay:
                    _log.info(
                        f"can repay {new_balance.repay} {base_asset} without requiring more funds"
                    )
                else:
                    # TODO: Implement
                    _log.error(
                        f"need to buy more {base_asset} to repay {new_balance.repay} but not "
                        "implemented"
                    )
                    raise Exception(f"Did not repay enough {base_asset}; balance {new_balance}")
                await self._user.repay(
                    exchange=position.exchange,
                    asset=base_asset,
                    size=new_balance.repay,
                    account=position.symbol,
                )
                new_balance = await self._user.get_balance(
                    exchange=position.exchange,
                    account=position.symbol,
                    asset=base_asset,
                )
                assert new_balance.repay == 0

            _log.info(
                f"transferring {closed_position.gain} {quote_asset} from {position.symbol} to "
                "spot account"
            )
            transfer_tasks = [
                self._user.transfer(
                    exchange=position.exchange,
                    asset=quote_asset,
                    size=closed_position.gain,
                    from_account=position.symbol,
                    to_account="spot",
                ),
            ]
            if new_balance.available > 0:
                _log.info(
                    f"transferring {new_balance.available} {base_asset} from {position.symbol} to "
                    "spot account"
                )
                transfer_tasks.append(
                    self._user.transfer(
                        exchange=position.exchange,
                        asset=base_asset,
                        size=new_balance.available,
                        from_account=position.symbol,
                        to_account="spot",
                    )
                )
            await asyncio.gather(*transfer_tasks)

        _log.info(f"closed short position {closed_position.symbol} {mode.name}")
        _log.debug(extract_public(closed_position))
        return closed_position

    # After repaying borrowed asset, Binance can still return the old repay balance. We retry
    # until the balance has changed.
    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(),
        retry=retry_if_exception_type(_UnexpectedExchangeResult),
        before_sleep=before_sleep_log(_log, logging.WARNING),
    )
    async def _get_repaid_balance_with_retries(
        self, exchange: str, account: str, asset: str, original_borrowed: Decimal
    ) -> Balance:
        balance = await self._user.get_balance(
            exchange=exchange,
            account=account,
            asset=asset,
        )
        if balance.borrowed == original_borrowed:
            raise _UnexpectedExchangeResult(
                f"Borrowed amount still {original_borrowed} for account {account} asset {asset}"
            )
        return balance


class SimulatedPositioner:
    def __init__(self, informant: Informant) -> None:
        self._informant = informant

    def open_simulated_positions(
        self,
        exchange: str,
        # [symbol, quote, short, time, price]
        entries: list[tuple[str, Decimal, bool, Timestamp, Decimal]],
    ) -> list[Position.Open]:
        return [
            self._open_simulated_short_position(exchange, symbol, time, price, quote)
            if short
            else self._open_simulated_long_position(exchange, symbol, time, price, quote)
            for symbol, quote, short, time, price in entries
        ]

    def close_simulated_positions(
        self,
        # [symbol, close reason, time, price]
        entries: list[tuple[Position.Open, CloseReason, Timestamp, Decimal]],
    ) -> list[Position.Closed]:
        return [
            self._close_simulated_short_position(pos, time, price, reason)
            if isinstance(pos, Position.OpenShort)
            else self._close_simulated_long_position(pos, time, price, reason)
            for pos, reason, time, price in entries
        ]

    def _open_simulated_long_position(
        self,
        exchange: str,
        symbol: str,
        time: Timestamp,
        price: Decimal,
        quote: Decimal,
    ) -> Position.OpenLong:
        base_asset, _ = unpack_assets(symbol)
        fees, filters = self._informant.get_fees_filters(exchange, symbol)

        size = filters.size.round_down(quote / price)
        if size == 0:
            raise BadOrder("Insufficient funds")
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(size * fees.taker, filters.base_precision)

        open_position = Position.OpenLong(
            exchange=exchange,
            symbol=symbol,
            time=time,
            fills=[Fill(price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset)],
        )
        _log.info(f"opened simulated long position {symbol} at {strftimestamp(time)}")
        return open_position

    def _close_simulated_long_position(
        self,
        position: Position.OpenLong,
        time: Timestamp,
        price: Decimal,
        reason: CloseReason,
    ) -> Position.Long:
        _, quote_asset = unpack_assets(position.symbol)
        fees, filters = self._informant.get_fees_filters(position.exchange, position.symbol)

        fills: list[Fill] = []
        size = filters.size.round_down(position.base_gain)
        if size > 0:
            quote = round_down(price * size, filters.quote_precision)
            fee = round_half_up(quote * fees.taker, filters.quote_precision)
            fills.append(Fill(price=price, size=size, quote=quote, fee=fee, fee_asset=quote_asset))
        # If size is 0, we cannot close the position anymore. This can happen if the amount bought
        # falls below min size filter due to fees, for example.

        closed_position = position.close(
            time=time,
            fills=fills,
            reason=reason,
        )
        _log.info(
            f"closed simulated long position {closed_position.symbol} at "
            f"{strftimestamp(time)} due to {reason.name}"
        )
        return closed_position

    def _open_simulated_short_position(
        self,
        exchange: str,
        symbol: str,
        time: Timestamp,
        price: Decimal,
        collateral: Decimal,
    ) -> Position.OpenShort:
        base_asset, quote_asset = unpack_assets(symbol)
        fees, filters = self._informant.get_fees_filters(exchange, symbol)
        limit = self._informant.get_borrow_info(
            exchange=exchange, asset=base_asset, account=symbol
        ).limit
        if limit == 0:
            raise BadOrder("Borrow limit zero")
        # TODO: We could get a maximum margin multiplier from the exchange and use that but use the
        # lowers multiplier for now for reduced risk.
        margin_multiplier = 2
        # margin_multiplier = self.informant.get_margin_multiplier(exchange)

        borrowed = _calculate_borrowed(filters, margin_multiplier, limit, collateral, price)
        quote = round_down(price * borrowed, filters.quote_precision)
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        open_position = Position.OpenShort(
            exchange=exchange,
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=time,
            fills=[Fill(price=price, size=borrowed, quote=quote, fee=fee, fee_asset=quote_asset)],
        )
        _log.info(f"opened simulated short position {symbol} at {strftimestamp(time)}")
        return open_position

    def _close_simulated_short_position(
        self,
        position: Position.OpenShort,
        time: Timestamp,
        price: Decimal,
        reason: CloseReason,
    ) -> Position.Short:
        base_asset, _ = unpack_assets(position.symbol)
        fees, filters = self._informant.get_fees_filters(position.exchange, position.symbol)
        asset_info = self._informant.get_asset_info(exchange=position.exchange, asset=base_asset)
        borrow_info = self._informant.get_borrow_info(
            exchange=position.exchange, asset=base_asset, account=position.symbol
        )

        interest = _calculate_interest(
            borrowed=position.borrowed,
            hourly_rate=borrow_info.hourly_interest_rate,
            start=position.time,
            end=time,
            precision=asset_info.precision,
        )
        size = position.borrowed + interest
        fee = round_half_up(size * fees.taker, filters.base_precision)
        size += fee
        quote = round_down(price * size, filters.quote_precision)

        closed_position = position.close(
            time=time,
            interest=interest,
            fills=[Fill(price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset)],
            reason=reason,
        )
        _log.info(
            f"closed simulated short position {closed_position.symbol} at "
            f"{strftimestamp(time)} due to {reason.name}"
        )
        return closed_position


def _calculate_borrowed(
    filters: Filters, margin_multiplier: int, limit: Decimal, collateral: Decimal, price: Decimal
) -> Decimal:
    collateral_size = filters.size.round_down(collateral / price)
    if collateral_size == 0:
        raise BadOrder("Collateral base size 0")
    borrowed = collateral_size * (margin_multiplier - 1)
    if borrowed == 0:
        raise BadOrder("Borrowed 0; incorrect margin multiplier?")
    return min(borrowed, limit)


def _calculate_interest(
    borrowed: Decimal, hourly_rate: Decimal, start: int, end: int, precision: int
) -> Decimal:
    duration = ceil_multiple(end - start, HOUR_MS) // HOUR_MS
    return round_half_up(borrowed * duration * hourly_rate, precision=precision)

from __future__ import annotations

import asyncio
import functools
import logging
import os
import platform
import shutil
import zlib
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cffi
import pandas as pd

from juno import (
    BorrowInfo, Candle, Fees, Filters, Interval, MissedCandlePolicy, Timestamp, strategies
)
from juno.cffi import CDefBuilder
from juno.components import Informant
from juno.filters import Price, Size
from juno.strategies import Strategy
from juno.time import DAY_MS
from juno.typing import ExcType, ExcValue, Traceback, get_input_type_hints
from juno.utils import home_path, list_concretes_from_module, unpack_symbol

from .solver import FitnessValues, Individual, Solver

_log = logging.getLogger(__name__)

_cdef_builder = CDefBuilder({
    Interval: 'uint64_t',
    Timestamp: 'uint64_t',
    str: 'uint32_t',  # Will be Adler32 checksum of the string.
})

_strategy_types = list_concretes_from_module(strategies, Strategy)

# (symbol, interval, start, end)
TimeSeriesKey = Tuple[str, Interval, Timestamp, Timestamp]

_DEFAULT_BORROW_INFO = BorrowInfo()


class Rust(Solver):
    def __init__(self, informant: Informant) -> None:
        self._informant = informant

        self._c_fees_filters: Dict[str, Tuple[Any, Any]] = {}
        self._c_borrow_infos: Dict[str, Any] = {}
        self._c_candles: Dict[TimeSeriesKey, Any] = {}
        self._c_prices: Dict[TimeSeriesKey, Any] = {}
        self._c_series: Dict[TimeSeriesKey, Any] = {}

    async def __aenter__(self) -> Rust:
        # Setup Rust src paths.
        src_dir = Path(os.path.dirname(os.path.realpath(__file__))) / '..' / '..'
        src_dir = src_dir.resolve()  # Simplify path.
        src_files = src_dir.glob('./juno_rs/**/*.rs')
        # Seconds-level precision.
        src_latest_mtime = max(int(f.stat().st_mtime) for f in src_files)

        # Setup Rust target paths.
        prefix, suffix = None, None
        system = platform.system()
        if system == 'Linux':
            prefix, suffix = 'lib', '.so'
        elif system == 'Windows':
            prefix, suffix = '', '.dll'
        else:
            raise Exception(f'unknown system ({system})')
        compiled_path = src_dir / 'target' / 'release' / f'{prefix}juno_rs{suffix}'
        dst_path = home_path() / f'juno_rs_{src_latest_mtime}{suffix}'

        # Build Rust and copy to dist folder if current version missing.
        if not dst_path.is_file():
            _log.info(f'compiling rust module with working directory {src_dir}')
            proc = await asyncio.create_subprocess_shell(
                'cargo build --release',
                cwd=src_dir,
                # stdout=asyncio.subprocess.PIPE,
                # stderr=asyncio.subprocess.PIPE,
            )
            _log.info('waiting for subprocess to complete')
            await proc.wait()
            if proc.returncode != 0:
                raise Exception(f'rust module compilation failed ({proc.returncode})')
            await asyncio.get_running_loop().run_in_executor(
                None, shutil.copy2, str(compiled_path), str(dst_path)
            )
            _log.info('rust module compiled')

        self._ffi = cffi.FFI()
        self._ffi.cdef(_build_cdef())
        _log.critical(_build_cdef())
        self._libjuno = await asyncio.get_running_loop().run_in_executor(
            None, self._ffi.dlopen, str(dst_path)
        )

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    def solve(self, config: Solver.Config, population: List[Individual]) -> List[FitnessValues]:
        # TODO: Pool resources?
        c_population = self._ffi.new(f'Individual[{len(population)}]')
        for i in range(len(population)):
            self._prepare_individual(config, population[i], c_population[i])
        c_fitnesses = self._ffi.new(f'FitnessValues[{len(population)}]')
        fn = getattr(self._libjuno, config.strategy_type.__name__.lower())
        # TODO: Run in a separate thread?
        _log.critical('NYYD ALGAA')
        fn(
            c_population,
            c_fitnesses,
            len(population),
        )
        _log.critical('NYYD LOPPE')
        return list(map(FitnessValues.from_object, c_fitnesses))

    def _prepare_individual(self, config: Solver.Config, ind: Individual, c_ind: Any) -> None:
        # Preparation.
        base_asset, _ = unpack_symbol(ind.symbol)
        # Trading.
        c_candles = self._get_or_create_c_candles(
            (ind.symbol, ind.interval, config.start, config.end),
            config.candles[(ind.symbol, ind.interval)],
        )
        fees, filters = self._informant.get_fees_filters(config.exchange, ind.symbol)
        c_fees, c_filters = self._get_or_create_c_fees_filters(ind.symbol, fees, filters)
        borrow_info = (
            self._informant.get_borrow_info(config.exchange, base_asset) if ind.short
            else _DEFAULT_BORROW_INFO
        )
        c_borrow_info = self._get_or_create_c_borrow_info(ind.symbol, borrow_info)
        margin_multiplier = self._informant.get_margin_multiplier(config.exchange)
        # Analysis.
        num_days = len(config.fiat_prices['btc'])
        analysis_interval = max(DAY_MS, ind.interval)
        c_quote_fiat_prices = self._get_or_create_c_prices(
            ('btc-eur', analysis_interval, config.start, config.end), config.fiat_prices['btc']
        )
        c_base_fiat_prices = self._get_or_create_c_prices(
            (f'{base_asset}-eur', analysis_interval, config.start, config.end),
            config.fiat_prices[base_asset],
        )
        c_benchmark_g_returns = self._get_or_create_c_series(
            ('btc-eur', analysis_interval, config.start, config.end), config.benchmark_g_returns
        )
        # Strategy.
        c_strategy_info = self._ffi.new(f'{config.strategy_type.__name__}Info *')
        for a, (n, t) in zip(
            ind.strategy_args,
            get_input_type_hints(config.strategy_type.__init__).items()
        ):
            value = _adler32(a) if t is str else a
            _log.critical(f'{n}: {value}')
            setattr(c_strategy_info, n, value)
        _log.critical(c_strategy_info)
        _log.critical(c_strategy_info.long_ma)

        # Individual
        # Analysis.
        c_ind.quote_fiat_prices = c_quote_fiat_prices
        c_ind.quote_fiat_prices_length = num_days
        c_ind.base_fiat_prices = c_base_fiat_prices
        c_ind.base_fiat_prices_length = num_days
        c_ind.benchmark_g_returns = c_benchmark_g_returns
        c_ind.benchmark_g_returns_length = config.benchmark_g_returns.size
        # Trading.
        c_ind.candles = c_candles
        c_ind.candles_length = len(config.candles)
        c_ind.fees = c_fees
        c_ind.filters = c_filters
        c_ind.borrow_info = c_borrow_info
        c_ind.margin_multiplier = margin_multiplier
        c_ind.interval = ind.interval
        c_ind.quote = config.quote
        c_ind.missed_candle_policy = ind.missed_candle_policy
        c_ind.stop_loss = ind.stop_loss
        c_ind.trail_stop_loss = ind.trail_stop_loss
        c_ind.take_profit = ind.take_profit
        c_ind.long_ = ind.long
        c_ind.short_ = ind.short
        # Strategy.
        c_ind.strategy_info = c_strategy_info

    def _get_or_create_c_fees_filters(self, key: str, fees: Fees, filters: Filters) -> Any:
        c_fees_filters = self._c_fees_filters.get(key)
        if not c_fees_filters:
            c_fees = self._ffi.new('Fees *')
            c_fees.maker = float(fees.maker)
            c_fees.taker = float(fees.taker)

            c_filters = self._ffi.new('Filters *')
            c_filters.price = {
                'min': float(filters.price.min),
                'max': float(filters.price.max),
                'step': float(filters.price.step),
            }
            c_filters.size = {
                'min': float(filters.size.min),
                'max': float(filters.size.max),
                'step': float(filters.size.step),
            }
            c_filters.base_precision = filters.base_precision
            c_filters.quote_precision = filters.quote_precision

            self._c_fees_filters[key] = c_fees, c_filters
            c_fees_filters = c_fees, c_filters
        return c_fees_filters

    def _get_or_create_c_borrow_info(self, key: str, borrow_info: BorrowInfo) -> Any:
        c_borrow_info = self._c_borrow_infos.get(key)
        if not c_borrow_info:
            c_borrow_info = self._ffi.new('BorrowInfo *')
            c_borrow_info.daily_interest_rate = float(borrow_info.daily_interest_rate)
            c_borrow_info.limit = float(borrow_info.limit)

            self._c_borrow_infos[key] = c_borrow_info
        return c_borrow_info

    def _get_or_create_c_candles(self, key: TimeSeriesKey, candles: List[Candle]) -> Any:
        c_candles = self._c_candles.get(key)
        if not c_candles:
            c_candles = self._ffi.new(f'Candle[{len(candles)}]')
            for i, c in enumerate(candles):
                c_candles[i] = {
                    'time': c[0],
                    'open': float(c[1]),
                    'high': float(c[2]),
                    'low': float(c[3]),
                    'close': float(c[4]),
                    'volume': float(c[5]),
                }
            self._c_candles[key] = c_candles
        return c_candles

    def _get_or_create_c_prices(self, key: TimeSeriesKey, prices: List[Decimal]) -> Any:
        c_prices = self._c_prices.get(key)
        if not c_prices:
            c_prices = self._ffi.new(f'double[{len(prices)}]')
            for i, p in enumerate(prices):
                c_prices[i] = p
            self._c_prices[key] = c_prices
        return c_prices

    def _get_or_create_c_series(self, key: TimeSeriesKey, series: pd.Series) -> Any:
        c_series = self._c_series.get(key)
        if not c_series:
            c_series = self._ffi.new(f'double[{series.size}]')
            for i, p in enumerate(series.values):
                c_series[i] = p
            self._c_series[key] = c_series
        return c_series


def _build_cdef() -> str:
    members = [
        _cdef_builder.struct(Candle, exclude=['closed']),
        _cdef_builder.struct(Fees),
        _cdef_builder.struct(Price),
        _cdef_builder.struct(Size),
        _cdef_builder.struct(Filters, exclude=['percent_price', 'min_notional']),
        _cdef_builder.struct(BorrowInfo),
        _cdef_builder.struct(FitnessValues),
        _cdef_builder.struct_from_fields(
            'Individual',
            # Analysis.
            ('quote_fiat_prices', List[Decimal]),
            ('base_fiat_prices', List[Decimal]),
            ('benchmark_g_returns', List[Decimal]),
            # Trading.
            ('candles', List[Candle]),
            ('fees', Fees),
            ('filters', Filters),
            ('borrow_info', BorrowInfo),
            ('margin_multiplier', int),
            ('interval', Interval),
            ('quote', Decimal),
            ('missed_candle_policy', MissedCandlePolicy),
            ('stop_loss', Decimal),
            ('trail_stop_loss', bool),
            ('take_profit', Decimal),
            ('long_', bool),
            ('short_', bool),
            # Strategy.
            ('strategy_info', None),
            refs=['fees', 'filters', 'borrow_info', 'strategy_info'],
        ),
    ]

    for strategy_type in _strategy_types:
        strategy_name_lower = strategy_type.__name__.lower()
        strategy_info_type_name = f'{strategy_type.__name__}Info'
        members.append(_cdef_builder.struct_from_fields(
            strategy_info_type_name,
            *iter(get_input_type_hints(strategy_type.__init__).items())  # type: ignore
        ))
        members.append(_cdef_builder.function_from_params(
            strategy_name_lower,
            None,
            ('population', type('Individual', (), {})),
            ('fitnesses', type('FitnessValues', (), {})),
            ('length', int),
            refs=['population', 'fitnesses']
        ))

    return '\n'.join(members)


@functools.lru_cache
def _adler32(value: str) -> int:
    return zlib.adler32(value.encode())

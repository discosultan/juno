from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Tuple, Type

import cffi
import pandas as pd

from juno import Candle, Fees, Filters, Interval, Timestamp
from juno.cffi import CDefBuilder
from juno.components import Chandler, Informant
from juno.filters import Price, Size
from juno.strategies import MAMACX, Strategy
from juno.time import DAY_MS
from juno.trading import MissedCandlePolicy, Statistics
from juno.typing import ExcType, ExcValue, Traceback, get_input_type_hints
from juno.utils import home_path

from .solver import Solver, SolverResult

_log = logging.getLogger(__name__)

_cdef_builder = CDefBuilder({
    Interval: 'uint64_t',
    Timestamp: 'uint64_t',
})


class AnalysisInfo(NamedTuple):
    base_fiat_candles: List[Candle]
    portfolio_candles: List[Candle]
    benchmark_g_returns: pd.Series


class TradingInfo(NamedTuple):
    candles: List[Candle]
    fees: Fees
    filters: Filters
    interval: Interval
    quote: Decimal
    missed_candle_policy: MissedCandlePolicy
    trailing_stop: Decimal


class Rust(Solver):
    def __init__(self, chandler: Chandler, informant: Informant) -> None:
        self.chandler = chandler
        self.informant = informant
        self.c_candles: Dict[Tuple[str, int], Any] = {}
        self.c_benchmark_g_returns: Any = None
        self.c_fees_filters: Dict[str, Tuple[Any, Any]] = {}

    async def __aenter__(self) -> Rust:
        # Setup Rust src paths.
        src_dir = Path(os.path.dirname(os.path.realpath(__file__))) / '..' / '..'
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
            _log.info('compiling rust module')
            proc = await asyncio.create_subprocess_shell('cargo build --release', cwd=src_dir)
            await proc.communicate()
            if proc.returncode != 0:
                raise Exception(f'rust module compilation failed ({proc.returncode})')
            await asyncio.get_running_loop().run_in_executor(
                None, shutil.copy2, str(compiled_path), str(dst_path)
            )

        self.ffi = cffi.FFI()
        self.ffi.cdef(_build_cdef())
        self.libjuno = await asyncio.get_running_loop().run_in_executor(
            None, self.ffi.dlopen, str(dst_path)
        )

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    def solve(
        self,
        base_fiat_candles: List[Candle],
        portfolio_candles: List[Candle],
        benchmark_stats: Statistics,
        strategy_type: Type[Strategy],
        quote: Decimal,
        candles: List[Candle],
        fees: Fees,
        filters: Filters,
        symbol: str,
        interval: Interval,
        missed_candle_policy: MissedCandlePolicy,
        trailing_stop: Decimal,
        *args: Any,
    ) -> SolverResult:
        c_base_fiat_candles = self._get_or_create_c_candles(('btc-eur', DAY_MS), base_fiat_candles)
        c_portfolio_candles = self._get_or_create_c_candles((symbol, DAY_MS), portfolio_candles)

        # if not self.c_benchmark_g_returns:
        #     self.c_benchmark_g_returns = self._build_c_benchmark_g_returns(benchmark_stats)

        c_candles = self._get_or_create_c_candles((symbol, interval), candles)
        c_fees, c_filters = self._get_or_create_c_fees_filters(symbol, fees, filters)

        c_analysis_info = self.ffi.new('AnalysisInfo *')
        c_analysis_info.base_fiat_candles = c_base_fiat_candles
        c_analysis_info.base_fiat_candles_length = len(c_base_fiat_candles)
        c_analysis_info.portfolio_candles = c_portfolio_candles
        c_analysis_info.portfolio_candles_length = len(c_portfolio_candles)
        # c_analysis_info.benchmark_g_returns =

        c_trading_info = self.ffi.new('TradingInfo *')
        c_trading_info.candles = c_candles
        c_trading_info.candles_length = len(c_candles)
        c_trading_info.fees = c_fees
        c_trading_info.filters = c_filters
        c_trading_info.interval = interval
        c_trading_info.quote = float(quote)  # TODO: do we need to cast here?????
        c_trading_info.missed_candle_policy = missed_candle_policy
        c_trading_info.trailing_stop = float(trailing_stop)

        c_strategy_info = self.ffi.new(f'{strategy_type.__name__}Info')
        c_strategy_info.short_period = args[0]
        c_strategy_info.long_period = args[1]
        c_strategy_info.neg_threshold = args[2]
        c_strategy_info.pos_threshold = args[3]
        c_strategy_info.short_ma = args[4]
        c_strategy_info.long_ma = args[5]

        fn = getattr(self.libjuno, strategy_type.__name__.lower())
        result = fn(c_analysis_info, c_trading_info, c_strategy_info)
        return SolverResult.from_object(result)

    def _get_or_create_c_candles(self, key: Tuple[str, int], candles: List[Candle]) -> Any:
        c_candles = self.c_candles.get(key)
        if not c_candles:
            c_candles = self.ffi.new(f'Candle[{len(candles)}]')
            for i, c in enumerate(candles):
                c_candles[i] = {
                    'time': c[0],
                    'open': float(c[1]),
                    'high': float(c[2]),
                    'low': float(c[3]),
                    'close': float(c[4]),
                    'volume': float(c[5]),
                }
            self.c_candles[key] = c_candles
        return c_candles

    def _build_c_benchmark_g_returns(self, stats: Statistics) -> Any:
        np_array = stats.g_returns.to_numpy()
        pointer = self.ffi.cast('double *', np_array.ctypes.data)
        return pointer, np_array

    def _get_or_create_c_fees_filters(self, key: str, fees: Fees, filters: Filters) -> Any:
        c_fees_filters = self.c_fees_filters.get(key)
        if not c_fees_filters:
            c_fees = self.ffi.new('Fees *')
            c_fees.maker = float(fees.maker)
            c_fees.taker = float(fees.taker)

            c_filters = self.ffi.new('Filters *')
            c_filters.base_precision = filters.base_precision
            c_filters.quote_precision = filters.quote_precision
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

            self.c_fees_filters[key] = c_fees, c_filters
            c_fees_filters = c_fees, c_filters
        return c_fees_filters


def _build_cdef() -> str:
    # TODO: Do we want to parametrize this? Or lookup from module and construct for all.
    strategy_type = MAMACX
    strategy_name_lower = strategy_type.__name__.lower()
    strategy_info_name = f'{strategy_type.__name__}Info'

    return ''.join((
        _cdef_builder.struct(Candle, exclude=['closed']),
        _cdef_builder.struct(Fees),
        _cdef_builder.struct(Price),
        _cdef_builder.struct(Size),
        _cdef_builder.struct(Filters, exclude=['percent_price', 'min_notional']),
        _cdef_builder.struct(SolverResult),
        _cdef_builder.struct_from_fields(
            'AnalysisInfo',
            ('base_fiat_candles', List[Candle]),
            ('portfolio_candles', List[Candle])
            # ('benchmark_g_returns', pd.Series)
        ),
        _cdef_builder.struct_from_fields(
            'TradingInfo',
            ('candles', List[Candle]),
            ('fees', Fees),
            ('filters', Filters),
            ('interval', Interval),
            ('quote', Decimal),
            ('missed_candle_policy', MissedCandlePolicy),
            ('trailing_stop', Decimal)
        ),
        _cdef_builder.struct_from_fields(
            strategy_info_name,
            *iter(get_input_type_hints(strategy_type.__init__).items())
        ),
        _cdef_builder.function_from_params(
            strategy_name_lower,
            SolverResult,
            ('analysis_info', AnalysisInfo),
            ('trading_info', TradingInfo),
            (f'{strategy_name_lower}_info', type(strategy_info_name, (), {}))
        ),
    ))

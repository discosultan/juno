from __future__ import annotations

import asyncio
import inspect
import logging
import os
import platform
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple, Type

import cffi
import pandas as pd

from juno import Candle, Fees, Filters, Interval, Timestamp, strategies
from juno.cffi import CDefBuilder
from juno.components import Chandler, Informant
from juno.filters import Price, Size
from juno.strategies import Strategy
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

_strategy_types = [
    t for n, t in inspect.getmembers(
        strategies,
        lambda m: inspect.isclass(m) and not inspect.isabstract(m) and issubclass(m, Strategy)
    )
]


class Rust(Solver):
    def __init__(self, chandler: Chandler, informant: Informant) -> None:
        self.chandler = chandler
        self.informant = informant
        self.c_candles: Dict[Tuple[str, int, bool], Any] = {}
        self.c_fees_filters: Dict[str, Tuple[Any, Any]] = {}
        self.c_series: Dict[str, Any] = {}
        self.keep_alive: List[Any] = []

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

        self.c_analysis_info = self.ffi.new('AnalysisInfo *')
        self.c_trading_info = self.ffi.new('TradingInfo *')
        self.c_strategy_infos = {
            t: self.ffi.new(f'{t.__name__}Info *') for t in _strategy_types
        }

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    def solve(
        self,
        quote_fiat_candles: List[Candle],
        symbol_candles: List[Candle],
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
        # Trading.
        c_candles = self._get_or_create_c_candles((symbol, interval, False), candles)
        c_fees, c_filters = self._get_or_create_c_fees_filters(symbol, fees, filters)

        c_trading_info = self.c_trading_info
        c_trading_info.candles = c_candles
        c_trading_info.candles_length = len(candles)
        c_trading_info.fees = c_fees
        c_trading_info.filters = c_filters
        c_trading_info.interval = interval
        c_trading_info.quote = quote
        c_trading_info.missed_candle_policy = missed_candle_policy
        c_trading_info.trailing_stop = trailing_stop

        # Strategy.
        c_strategy_info = self.c_strategy_infos[strategy_type]
        for i, n in enumerate(get_input_type_hints(strategy_type.__init__).keys()):
            setattr(c_strategy_info, n, args[i])

        # Analysis.
        c_quote_fiat_daily = self._get_or_create_c_candles(
            ('btc-eur', DAY_MS, True), quote_fiat_candles
        )
        # c_portfolio_candles = self._get_or_create_c_candles((symbol, DAY_MS), symbol_candles)
        c_base_fiat_daily = self._get_c_base_fiat_daily(symbol, quote_fiat_candles, symbol_candles)

        c_benchmark_g_returns = self._get_or_create_c_series(
            'benchmark_g_returns', benchmark_stats.g_returns
        )

        c_analysis_info = self.c_analysis_info
        c_analysis_info.quote_fiat_daily = c_quote_fiat_daily
        c_analysis_info.quote_fiat_daily_length = len(quote_fiat_candles)
        c_analysis_info.base_fiat_daily = c_base_fiat_daily
        c_analysis_info.base_fiat_daily_length = len(symbol_candles)
        c_analysis_info.benchmark_g_returns = c_benchmark_g_returns
        c_analysis_info.benchmark_g_returns_length = benchmark_stats.g_returns.size

        # Go!
        fn = getattr(self.libjuno, strategy_type.__name__.lower())
        result = fn(c_trading_info, c_strategy_info, c_analysis_info)
        return SolverResult.from_object(result)

    # TODO: Temp! Noob! Move out of solver! Must be computed in optimizer!
    def _get_c_base_fiat_daily(self, symbol, quote_fiat_daily, symbol_daily) -> Any:
        c_base_fiat_daily = self.c_series.get(symbol)  # TODO: WTF
        if not c_base_fiat_daily:
            assert len(quote_fiat_daily) == len(symbol_daily), (
                f'{len(quote_fiat_daily)=} {len(symbol_daily)=}'
            )
            c_base_fiat_daily = self.ffi.new(f'double[{len(quote_fiat_daily)}]')
            for i, (qfd, sd) in enumerate(zip(quote_fiat_daily, symbol_daily)):
                c_base_fiat_daily[i] = sd.close * qfd.close
            self.c_series[symbol] = c_base_fiat_daily
        return c_base_fiat_daily

    def _get_or_create_c_candles(self, key: Tuple[str, int, bool], candles: List[Candle]) -> Any:
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

    def _get_or_create_c_series(self, key: str, series: pd.Series) -> Any:
        c_series = self.c_series.get(key)
        if not c_series:
            np_array = series.to_numpy()
            self.keep_alive.append(np_array)
            c_series = self.ffi.cast('double *', np_array.ctypes.data)
            self.c_series[key] = c_series
        return c_series


def _build_cdef() -> str:
    members = [
        _cdef_builder.struct(Candle, exclude=['closed']),
        _cdef_builder.struct(Fees),
        _cdef_builder.struct(Price),
        _cdef_builder.struct(Size),
        _cdef_builder.struct(Filters, exclude=['percent_price', 'min_notional']),
        _cdef_builder.struct(SolverResult),
        _cdef_builder.struct_from_fields(
            'AnalysisInfo',
            ('quote_fiat_daily', List[Candle]),
            ('base_fiat_daily', List[Decimal]),
            ('benchmark_g_returns', List[Decimal])
        ),
        _cdef_builder.struct_from_fields(
            'TradingInfo',
            ('candles', List[Candle]),
            ('fees', Fees),
            ('filters', Filters),
            ('interval', Interval),
            ('quote', Decimal),
            ('missed_candle_policy', MissedCandlePolicy),
            ('trailing_stop', Decimal),
            refs=['fees', 'filters']
        )
    ]

    for strategy_type in _strategy_types:
        _log.critical(strategy_type)
        strategy_name_lower = strategy_type.__name__.lower()
        strategy_info_type_name = f'{strategy_type.__name__}Info'
        strategy_info_param_name = f'{strategy_name_lower}_info'
        members.append(_cdef_builder.struct_from_fields(
            strategy_info_type_name,
            *iter(get_input_type_hints(strategy_type.__init__).items())  # type: ignore
        ))
        members.append(_cdef_builder.function_from_params(
            strategy_name_lower,
            SolverResult,
            ('trading_info', type('TradingInfo', (), {})),
            (strategy_info_param_name, type(strategy_info_type_name, (), {})),
            ('analysis_info', type('AnalysisInfo', (), {})),
            refs=['analysis_info', 'trading_info', strategy_info_param_name]
        ))

    return ''.join(members)

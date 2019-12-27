from __future__ import annotations

import asyncio
import itertools
import logging
import os
import platform
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple, Type

import cffi

from juno import Candle, Fees, Filters, Interval
from juno.components import Chandler, Informant
from juno.strategies import MAMACX, Meta, Strategy
from juno.typing import ExcType, ExcValue, Traceback, get_input_type_hints
from juno.utils import home_path

from .solver import Solver, SolverResult

_log = logging.getLogger(__name__)


class Rust(Solver):
    def __init__(self, chandler: Chandler, informant: Informant) -> None:
        self.chandler = chandler
        self.informant = informant
        self.c_candles: Dict[Tuple[str, int], Any] = {}
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
        strategy_type: Type[Strategy],
        quote: Decimal,
        candles: List[Candle],
        fees: Fees,
        filters: Filters,
        symbol: str,
        interval: Interval,
        missed_candle_policy: int,
        trailing_stop: Decimal,
        *args: Any,
    ) -> SolverResult:
        c_candles = self.c_candles.get((symbol, interval))
        if not c_candles:
            c_candles = self._build_c_candles(candles)
            self.c_candles[(symbol, interval)] = c_candles

        c_fees_filters = self.c_fees_filters.get(symbol)
        if not c_fees_filters:
            c_fees_filters = self._build_c_fees_filters(fees, filters)
            self.c_fees_filters[symbol] = c_fees_filters

        meta = strategy_type.meta
        format_args = {
            k: v
            for k, v in zip(meta.identifier_params, meta.get_identifier_args(args))
        }
        fn_name = meta.identifier.format(**format_args)
        fn = getattr(self.libjuno, fn_name)
        result = fn(
            c_candles,
            len(c_candles),
            *c_fees_filters,
            interval,
            float(quote),
            missed_candle_policy,
            trailing_stop,
            *meta.get_non_identifier_args(args),
        )
        return SolverResult.from_object(result)

    def _build_c_candles(self, candles: List[Candle]) -> Any:
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
        return c_candles

    def _build_c_fees_filters(self, fees: Fees, filters: Filters) -> Any:
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

        return c_fees, c_filters


def _build_cdef() -> str:
    # TODO: Do we want to parametrize this? Or lookup from module and construct for all.
    strategy_type = MAMACX
    type_hints = get_input_type_hints(strategy_type.__init__)
    meta = strategy_type.meta
    custom_params = ',\n    '.join(
        (f'{_map_type(v)} {k}' for k, v in type_hints.items() if k in meta.non_identifier_params)
    )

    return f'''
typedef struct {{
    uint64_t time;
    double open;
    double high;
    double low;
    double close;
    double volume;
}} Candle;

typedef struct {{
    double maker;
    double taker;
}} Fees;

typedef struct {{
    double min;
    double max;
    double step;
}} Price;

typedef struct {{
    double min;
    double max;
    double step;
}} Size;

typedef struct {{
    uint32_t base_precision;
    uint32_t quote_precision;
    Price price;
    Size size;
}} Filters;

{_build_backtest_result()}

{_build_function_permutations(meta, custom_params)}
    '''


def _build_backtest_result() -> str:
    fields = "\n    ".join(
        (f"{_map_meta_type(t)} {k};"
         for k, (t, _) in SolverResult.meta(include_disabled=True).items())
    )
    return f'''
typedef struct {{
    {fields}
}} BacktestResult;
    '''


def _build_function_permutations(meta: Meta, custom_params: str) -> str:
    templates = []
    possible_values = []
    for key in meta.identifier_params:
        # TODO: Generalize?
        possible_values.append(meta.constraints[key].choices)  # type: ignore
    for keys, values in zip(
        itertools.repeat(meta.identifier_params), itertools.product(*possible_values)
    ):
        format_args = {k: v for k, v in zip(keys, values)}
        templates.append(
            f'''
BacktestResult {meta.identifier.format(**format_args)}(
    const Candle *candles,
    uint32_t length,
    const Fees *fees,
    const Filters *filters,
    uint64_t interval,
    double quote,
    uint32_t missed_candle_policy,
    double trailing_stop,
    {custom_params});
        '''
        )
    return '\n'.join(templates)


# TODO: Consolidate mappings below? Use NewType? Use meta only?


def _map_meta_type(type_: str) -> str:
    result = {
        'u32': 'uint32_t',
        'u64': 'uint64_t',
        'f64': 'double',
    }.get(type_)
    if not result:
        raise NotImplementedError(f'Type mapping for CFFI not implemented ({type_})')
    return result


def _map_type(type_: type) -> str:
    result = {
        int: 'uint32_t',
        float: 'double',
        Decimal: 'double',
    }.get(type_)
    if not result:
        raise NotImplementedError(f'Type mapping for CFFI not implemented ({type_})')
    return result

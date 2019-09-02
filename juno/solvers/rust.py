from __future__ import annotations

import asyncio
# import functools
import logging
import os
import platform
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Type

import cffi

from .solver import Solver
from juno.asyncio import list_async
from juno.components import Informant
from juno.strategies import Strategy
from juno.typing import ExcType, ExcValue, Traceback, get_input_type_hints
from juno.utils import flatten, home_path

_log = logging.getLogger(__name__)


class Rust(Solver):
    def __init__(self, informant: Informant) -> None:
        self.informant = informant
        self.solve_native: Any = None

    async def __aenter__(self) -> Rust:
        # Setup Rust src paths.
        src_dir = Path(os.path.dirname(os.path.realpath(__file__))) / '..' / '..'
        src_files = src_dir.glob('./juno_rs/**/*.rs')
        # Seconds-level precision.
        src_latest_mtime = max((int(f.stat().st_mtime) for f in src_files))

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
                None,
                shutil.copy2,
                str(compiled_path),
                str(dst_path)
            )

        # FFI.
        # We need to keep a references to these instances for Rust; otherwise GC will clean them
        # up! Hence we assign to self.
        self.ffi = cffi.FFI()
        self.libjuno = self.ffi.dlopen(str(dst_path))

        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        pass

    async def get(
        self, strategy_type: Type[Strategy], exchange: str, symbol: str, interval: int, start: int,
        end: int, quote: Decimal
    ) -> Callable[..., Any]:
        self.ffi.cdef(_build_cdef(strategy_type))

        candles = await list_async(
            self.informant.stream_candles(exchange, symbol, interval, start, end)
        )
        fees = self.informant.get_fees(exchange, symbol)
        filters = self.informant.get_filters(exchange, symbol)

        # # FFI.
        # # We need to keep a references to these instances for Rust; otherwise GC will clean them
        # # up! Hence we assign to self.
        # self.ffi = cffi.FFI()
        # self.ffi.cdef(_build_cdef(strategy_type))
        # self.libjuno = self.ffi.dlopen(str(self.path))

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

        c_fees = self.ffi.new('Fees *')
        c_fees.maker = float(fees.maker)
        c_fees.taker = float(fees.taker)

        c_filters = self.ffi.new('Filters *')
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

        # solve_native = functools.partial(
        #     getattr(self.libjuno, strategy_type.__name__.lower()), c_candles, len(candles), c_fees,
        #     c_filters, interval, start, end, float(quote)
        # )

        def backtest(*args: Any) -> Any:
            invoke_args = []
            ident_args = []
            for arg in args:
                if isinstance(arg, str):
                    ident_args.append(arg)
                else:
                    invoke_args.append(arg)
            fn_name = ''.join(ident_args) + 'cx'

            self.ffi.cdef(_build_cdef(strategy_type))

            fn = getattr(self.libjuno, fn_name)
            result = fn(*invoke_args)
            # result = solve_native(*args)
            return (
                result.profit,
                result.mean_drawdown,
                result.max_drawdown,
                result.mean_position_profit,
                result.mean_position_duration,
            )

        return backtest


def _build_cdef(strategy_type: Type[Strategy]) -> str:
    type_hints = get_input_type_hints(strategy_type.__init__)
    meta_keys = set(flatten(strategy_type.meta().keys()))
    custom_params = ',\n'.join(
        (f'{_map_type(v)} {k}' for k, v in type_hints.items() if k in meta_keys)
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
            Price price;
            Size size;
        }} Filters;

        typedef struct {{
            double profit;
            double mean_drawdown;
            double max_drawdown;
            double mean_position_profit;
            uint64_t mean_position_duration;
        }} BacktestResult;

        BacktestResult {strategy_type.__name__.lower()}(
            const Candle *candles,
            uint32_t length,
            const Fees *fees,
            const Filters *filters,
            uint64_t interval,
            uint64_t start,
            uint64_t end,
            double quote,
            {custom_params});
    '''


def _map_type(type_: type) -> str:
    result = {
        int: 'uint32_t',
        float: 'double',
        Decimal: 'double',
    }.get(type_)
    if not result:
        raise NotImplementedError(f'Type mapping for CFFI not implemented ({type_})')
    return result

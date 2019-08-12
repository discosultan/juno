from __future__ import annotations

import functools
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, List, get_type_hints

import cffi

from juno import Candle, Fees
from juno.filters import Filters
from juno.utils import home_path

_log = logging.getLogger(__name__)


class Rust:

    def __init__(self, candles: List[Candle], fees: Fees, filters: Filters, strategy_type,
                 quote) -> None:
        self.candles = [
            (c[0], float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]), c[6])
            for c in candles
        ]
        self.fees = fees
        self.filters = filters
        self.strategy_type = strategy_type
        self.quote = quote

        self.solve_native: Any = None
        self.refs: List[Any] = []

    async def __aenter__(self) -> Rust:
        # Setup Rust src paths.
        src_dir = Path(os.path.dirname(os.path.realpath(__file__))) / '..'
        _log.critical(src_dir)
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
            # TODO: Run on another thread.
            _log.info('compiling rust module')
            subprocess.run(['cargo', 'build', '--release'], cwd=src_dir)
            shutil.copy2(str(compiled_path), str(dst_path))

        # FFI.
        ffi = cffi.FFI()
        ffi.cdef(_build_cdef(self.strategy_type))

        libjuno = ffi.dlopen(str(dst_path))

        c_fees = ffi.new('Fees *')
        c_fees.maker = float(self.fees.maker)
        c_fees.taker = float(self.fees.taker)

        self.solve_native = functools.partial(
            getattr(libjuno, self.strategy_type.__name__.lower()),
            c_fees,
            self.quote)

        # We need to keep a references to these instances for Rust; otherwise GC will clean them up!
        self.refs.extend([
            ffi,
            libjuno,
            # candles,
        ])

        return self

    def solve(self, *args: Any):
        return self.solve_native(*args)


def _build_cdef(strategy_type):
    # type_hints = get_type_hints(strategy_type.__init__)
    # custom_params = ',\n'.join([f'{_map_type(v)} {k}' for k, v in type_hints.items()])
    return f'''
        typedef struct {{
            uint64_t time;
            double open;
            double high;
            double low;
            double close;
            double volume;
            bool closed;
        }} Candle;

        typedef struct {{
            double maker;
            double taker;
        }} Fees;

        typedef struct {{
            uint32_t base_precision;
            double min_qty;
            double max_qty;
            double qty_step_size;
        }} AssetPairInfo;

        typedef struct {{
            double profit;
            double mean_drawdown;
            double max_drawdown;
            double mean_position_profit;
            uint64_t mean_position_duration;
        }} BacktestResult;

        BacktestResult {strategy_type.__name__.lower()}(
            // const Candle *candles,
            // uint32_t length,
            const Fees *fees,
            double quote);
    '''


def _map_type(type_: type) -> str:
    result = {
        int: 'uint32_t',
        float: 'double',
    }.get(type_)
    if not result:
        raise NotImplementedError()
    return result

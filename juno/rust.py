import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

from juno.utils import home_path

_log = logging.getLogger(__name__)


def init() -> None:
    # Setup Rust src paths.
    src_dir = Path(os.path.dirname(os.path.realpath(__file__)), '..', '..', 'juno_rs')
    src_files = src_dir.glob('**/*.rs')
    # Seconds-level precision.
    src_latest_mtime = max((int(f.stat().st_mtime) for f in src_files))

    # Setup Rust target paths.
    prefix, suffix = None, None
    system = platform.system()
    if system == 'Linux':
        prefix, suffix = '.lib', '.so'
    elif system == 'Windows':
        prefix, suffix = '', '.dll'
    else:
        raise Exception(f'unknown system ({system})')
    compiled_path = src_dir.joinpath('target', 'release', f'{prefix}juno_rs{suffix}')
    dst_path = home_path().joinpath(f'juno_rs_{src_latest_mtime}{suffix}')

    # Build Rust and copy to dist folder if current version missing.
    if not dst_path.is_file():
        _log.info('compiling rust module')
        subprocess.run(['cargo', 'build', '--release'], cwd=src_dir)
        shutil.copy2(str(compiled_path), str(dst_path))


def _map_type(type_: type) -> str:
    result = {
        int: 'uint32_t',
        float: 'double',
    }.get(type_)
    if not result:
        raise NotImplementedError()
    return result

import inspect
import sys

from .python import Python
from .rust import Rust

__all__ = [
    'Python',
    'Rust',
    'get_solver_type',
]

_solvers = {
    name.lower(): obj
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass)
}


def get_solver_type(name: str) -> type:
    return _solvers[name]

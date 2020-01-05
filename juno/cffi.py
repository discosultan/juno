from decimal import Decimal
from enum import IntEnum
from typing import Any, Callable, List, Tuple, Type, get_type_hints

_CUSTOM_MAPPINGS = {}
_DEFAULT_MAPPINGS = {
    int: 'uint32_t',
    float: 'double',
    Decimal: 'double',
    IntEnum: 'uint32_t',
}


def register_custom_mapping(type_: Type[Any], c_type: str) -> None:
    _CUSTOM_MAPPINGS[type_] = c_type


def deregister_custom_mapping(type_: Type[Any]) -> None:
    del _CUSTOM_MAPPINGS[type_]


def build_function(function: Callable[..., Any]) -> str:
    hints = get_type_hints(function)
    params = ((k, v) for k, v in hints.items() if k != 'return')
    return build_function_from_params(function.__name__, hints['return'], *params)


def build_function_from_params(
    name: str, return_param: Type[Any], *params: Tuple[str, Type[Any]]
) -> str:
    param_strings = (f'\n    {_map_type(v)} {k}' for k, v in params)
    return f'{_map_type(return_param)} {name}({",".join(param_strings)});\n'


def build_struct(type_: Type[Any], exclude: List[str] = []) -> str:
    fields = (f'    {_map_type(v)} {k};\n' for k, v in get_type_hints(type_).items()
              if k not in exclude)
    return f'typedef struct {{\n{"".join(fields)}}} {type_.__name__};\n'


def _map_type(type_: Type[Any]) -> str:
    for k, v in _CUSTOM_MAPPINGS.items():
        if type_ is k:
            return v
    for k, v in _DEFAULT_MAPPINGS.items():
        if issubclass(type_, k):
            return v
    return type_.__name__
    # raise NotImplementedError(f'Type mapping for CFFI not implemented ({type_})')

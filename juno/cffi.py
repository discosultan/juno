from decimal import Decimal
from enum import IntEnum
from typing import (
    Any, Callable, Dict, Iterable, List, Optional, Tuple, Type, get_args, get_origin,
    get_type_hints
)

_DEFAULT_MAPPINGS = {
    int: 'uint32_t',
    float: 'double',
    Decimal: 'double',
    IntEnum: 'uint32_t',
}


class CDefBuilder:
    def __init__(self, custom_mappings: Dict[Type[Any], str] = {}) -> None:
        self._custom_mappings = custom_mappings

    def function(self, function: Callable[..., Any]) -> str:
        hints = get_type_hints(function)
        params = ((k, v) for k, v in hints.items() if k != 'return')
        return self.function_from_params(function.__name__, hints['return'], *params)

    def function_from_params(
        self, name: str, return_param: Optional[Type[Any]], *params: Tuple[str, Type[Any]],
        refs: List[str] = []
    ) -> str:
        param_strings = (
            f'\n    {self._map_type(v, is_ref=k in refs)} {k}' for k, v in _transform(params)
        )
        return f'{self._map_type(return_param)} {name}({",".join(param_strings)});\n'

    def struct(self, type_: Type[Any], exclude: List[str] = []) -> str:
        fields = ((k, v) for k, v in _transform(get_type_hints(type_).items()) if k not in exclude)
        return self.struct_from_fields(type_.__name__, *fields)

    def struct_from_fields(
        self, name: str, *fields: Tuple[str, Type[Any]], refs: List[str] = []
    ) -> str:
        field_strings = (
            f'    {self._map_type(v, is_ref=k in refs)} {k};\n' for k, v in _transform(fields)
        )
        return f'typedef struct {{\n{"".join(field_strings)}}} {name};\n'

    def _map_type(self, type_: Optional[Type[Any]], is_ref: bool = False) -> str:
        for k, v in self._custom_mappings.items():
            if type_ is k:
                return v

        if type_ is None:
            return 'void'

        if get_origin(type_) is list:
            return f'const {self._map_type(get_args(type_)[0])}*'

        for k, v in _DEFAULT_MAPPINGS.items():
            if issubclass(type_, k):
                return v

        # raise NotImplementedError(f'Type mapping for CFFI not implemented ({type_})')
        if is_ref:
            return f'const {type_.__name__}*'
        else:
            return type_.__name__


def _transform(items: Iterable[Tuple[str, Type[Any]]]) -> Iterable[Tuple[str, Type[Any]]]:
    for k, v in items:
        yield k, v
        if get_origin(v) is list:
            yield f'{k}_length', int

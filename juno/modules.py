import importlib
import inspect
from types import ModuleType
from typing import Any, Dict, List, Type


def map_module_types(module: ModuleType) -> Dict[str, Type[Any]]:
    return {n.lower(): t for n, t in inspect.getmembers(module, inspect.isclass)}


# Cannot use typevar T in place of Any here. Triggers: "Only concrete class can be given where type
# is expected".
# Ref: https://github.com/python/mypy/issues/5374
def list_concretes_from_module(module: ModuleType, abstract: Type[Any]) -> List[Type[Any]]:
    return [t for _n, t in inspect.getmembers(
        module,
        lambda m: inspect.isclass(m) and not inspect.isabstract(m) and issubclass(m, abstract)
    )]


def get_module_type(module: ModuleType, name: str) -> Type[Any]:
    name_lower = name.lower()
    found_members = inspect.getmembers(
        module,
        lambda obj: inspect.isclass(obj) and obj.__name__.lower() == name_lower
    )
    if len(found_members) == 0:
        raise ValueError(f'Type named "{name}" not found in module "{module.__name__}".')
    if len(found_members) > 1:
        raise ValueError(f'Found more than one type named "{name}" in module "{module.__name__}".')
    return found_members[0][1]


def get_fully_qualified_name(obj: Any) -> str:
    # We separate module and type with a '::' in order to more easily resolve these components
    # in reverse.
    type_ = obj if inspect.isclass(obj) else type(obj)
    return f'{type_.__module__}::{type_.__qualname__}'


def get_type_by_fully_qualified_name(name: str) -> Type[Any]:
    # Resolve module.
    module_name, type_name = name.split('::')
    module = importlib.import_module(module_name)

    # Resolve nested classes.
    type_ = None
    for sub_name in type_name.split('.'):
        type_ = getattr(type_ if type_ else module, sub_name)
    assert type_
    return type_

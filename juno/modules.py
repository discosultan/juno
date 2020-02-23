import inspect
from types import ModuleType
from typing import Any, Dict, List, Type


def map_module_types(module: ModuleType) -> Dict[str, type]:
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

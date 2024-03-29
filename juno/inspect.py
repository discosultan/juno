from __future__ import annotations

import importlib
import inspect
import itertools
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass, make_dataclass
from enum import Enum
from types import ModuleType
from typing import Any, Generic, Optional, Sequence, TypeVar, get_type_hints

T = TypeVar("T")


def isnamedtuple(obj: Any) -> bool:
    if not isinstance(obj, type):
        obj = type(obj)

    # Note that '_fields' is present only if the tuple has at least 1 field.
    return inspect.isclass(obj) and issubclass(obj, tuple) and bool(getattr(obj, "_fields", False))


def isenum(obj: Any) -> bool:
    return inspect.isclass(obj) and issubclass(obj, Enum)


def istypeddict(obj: Any) -> bool:
    return inspect.isclass(obj) and issubclass(obj, dict) and len(get_type_hints(obj)) > 0


def extract_public(obj: Any, exclude: Sequence[str] = []) -> Any:
    """Turns all public fields and properties of an object into typed output. Non-recursive."""

    type_ = type(obj)

    # TODO: We can cache the generated type based on input type.
    attrs = []
    vals = []

    # Fields.
    fields = (
        (n, v)
        for (n, v) in get_type_hints(type_).items()
        if not n.startswith("_") and n not in exclude
    )
    for name, field_type in fields:
        attrs.append((name, field_type))
        vals.append(getattr(obj, name))

    # Properties.
    props = [(n, v) for (n, v) in inspect.getmembers(type_, _isprop) if not n.startswith("_")]
    # Inspect orders members alphabetically. We want to preserve source ordering.
    props.sort(key=lambda prop: prop[1].fget.__code__.co_firstlineno)
    for name, prop in props:
        prop_type = get_type_hints(prop.fget)["return"]
        attrs.append((name, prop_type))
        vals.append(prop.fget(obj))

    output_type = make_dataclass(type_.__name__, attrs)
    return output_type(*vals)


def _isprop(v: object) -> bool:
    return isinstance(v, property)


def get_fully_qualified_name(type_: type[Any]) -> str:
    # We separate module and type with a '::' in order to more easily resolve these components
    # in reverse.
    return f"{type_.__module__}::{type_.__qualname__}"


def get_type_by_fully_qualified_name(name: str) -> type[Any]:
    # Resolve module.
    module_name, type_name = name.split("::")
    module = importlib.import_module(module_name)

    # Resolve nested classes. We do not support function local classes.
    type_ = None
    for sub_name in type_name.split("."):
        type_ = getattr(type_ if type_ else module, sub_name)
    assert type_
    return type_


def construct(type_: type[T], *args, **kwargs) -> T:
    type_hints = get_type_hints(type_)
    final_kwargs = {}
    for d in itertools.chain(map(_asdict, args), [kwargs]):
        final_kwargs.update({k: v for k, v in d.items() if k in type_hints.keys()})
    return type_(**final_kwargs)  # type: ignore


def _asdict(a: Any) -> dict:
    if isinstance(a, dict):
        return a
    if is_dataclass(a):
        return asdict(a)
    if isnamedtuple(a):
        return a._asdict()
    return a.__dict__


def map_concrete_module_types(
    module: ModuleType, abstract: Optional[type[Any]] = None
) -> dict[str, type[Any]]:
    return {
        n.lower(): t
        for n, t in inspect.getmembers(
            module,
            lambda c: (
                inspect.isclass(c)
                and not inspect.isabstract(c)
                and (True if abstract is None else issubclass(c, abstract))
            ),
        )
    }


def map_type_parent_module_types(type_: type[Any]) -> dict[str, type[Any]]:
    module_name = type_.__module__
    parent_module_name = module_name[0 : module_name.rfind(".")]
    return map_concrete_module_types(sys.modules[parent_module_name])


# Cannot use typevar T in place of Any here. Triggers: "Only concrete class can be given where type
# is expected".
# Ref: https://github.com/python/mypy/issues/5374
def list_concretes_from_module(module: ModuleType, abstract: type[Any]) -> list[type[Any]]:
    return [
        t
        for _n, t in inspect.getmembers(
            module,
            lambda m: inspect.isclass(m) and not inspect.isabstract(m) and issubclass(m, abstract),
        )
    ]


def get_module_type(module: ModuleType, name: str) -> type[Any]:
    name_lower = name.lower()
    found_members = inspect.getmembers(
        module, lambda obj: inspect.isclass(obj) and obj.__name__.lower() == name_lower
    )
    if len(found_members) == 0:
        raise ValueError(f'Type named "{name}" not found in module "{module.__name__}".')
    if len(found_members) > 1:
        raise ValueError(f'Found more than one type named "{name}" in module "{module.__name__}".')
    return found_members[0][1]


class Constructor(ABC, Generic[T]):
    @abstractmethod
    def construct(self) -> T:
        pass


@dataclass(frozen=True)
class GenericConstructor(Constructor[T]):
    # Fully qualified name. We need to use this instead of a `type` in order to be able to
    # serialize it.
    name: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)

    def construct(self) -> T:
        return self.type_(*self.args, **self.kwargs)  # type: ignore

    @property
    def type_(self) -> type[T]:
        return get_type_by_fully_qualified_name(self.name)

    @staticmethod
    def from_type(type_: type[T], *args: Any, **kwargs: Any) -> GenericConstructor:
        return GenericConstructor(
            name=get_fully_qualified_name(type_),
            args=args,
            kwargs=kwargs,
        )

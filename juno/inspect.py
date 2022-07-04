from __future__ import annotations

import importlib
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


def isnamedtuple(obj: Any) -> bool:
    if not isinstance(obj, type):
        obj = type(obj)

    # Note that '_fields' is present only if the tuple has at least 1 field.
    return inspect.isclass(obj) and issubclass(obj, tuple) and bool(getattr(obj, "_fields", False))


def isenum(obj: Any) -> bool:
    return inspect.isclass(obj) and issubclass(obj, Enum)


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

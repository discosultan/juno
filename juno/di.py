from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Hashable
from types import TracebackType
from typing import Any, Callable, Iterable, Optional, TypeVar, get_args

from typing_inspect import is_optional_type

from .itertools import recursive_iter
from .typing import get_input_type_hints

T = TypeVar("T")

_log = logging.getLogger(__name__)


# All deps are handled as singleton. For transient lifetime, additional impl is required.
# Only type based resolution is applied. For name/type resolution, additional impl is required.
# If type registering was purely explicit, we could start using `resolve` after `__aenter__`.
class Container:
    def __init__(self) -> None:
        self._singleton_instances: dict[type[Any], Callable[[], Any]] = {}
        self._singleton_types: dict[type[Any], Callable[[], type[Any]]] = {}
        self._singletons: dict[type[Any], Any] = {}

    async def __aenter__(self) -> Container:
        _log.info(f"created instances: {list(self._singletons.values())}")
        for deps in list_dependencies_in_init_order(map_dependencies(self._singletons)):
            _log.info(f"entering: {deps}")
            await asyncio.gather(*(d.__aenter__() for d in deps if getattr(d, "__aenter__", None)))
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        for deps in reversed(list_dependencies_in_init_order(map_dependencies(self._singletons))):
            _log.info(f"exiting: {deps}")
            await asyncio.gather(
                *(d.__aexit__(exc_type, exc, tb) for d in deps if getattr(d, "__aexit__", None))
            )

    def add_singleton_instance(self, type_: Any, factory: Callable[[], Any]) -> None:
        self._singleton_instances[type_] = factory

    def add_singleton_types(self, types: Iterable[Any]) -> None:
        for type_ in types:
            self.add_singleton_type(type_)

    def add_singleton_type(
        self, type_: Any, factory: Optional[Callable[[], type[Any]]] = None
    ) -> None:
        self._singleton_types[type_] = factory if factory else lambda: type_

    def resolve(
        self, type_: Any, is_root: bool = True, default: Any = inspect.Parameter.empty
    ) -> Any:
        # Resolution priority:
        # 1. singleton
        # 2. instance factory
        # 3. type factory
        # 4. construct implicitly if is_root
        # 5. default value

        type_ = get_args(type_)[0] if is_optional_type(type_) else type_

        # 1. singleton
        instance = self._singletons.get(type_)
        if instance:
            return instance

        # 2. instance factory
        instance_factory = self._singleton_instances.get(type_)
        instance = inspect.Parameter.empty
        if instance_factory:
            try:
                instance = instance_factory()
            except Exception:
                _log.info(f"instance factory registered but unable to resolve for {type_}")
        if instance is inspect.Parameter.empty:
            # 3. type factory
            type_factory = self._singleton_types.get(type_)
            instance_type = None
            if type_factory:
                try:
                    instance_type = type_factory()
                except Exception:
                    _log.info(f"type factory registered but unable to resolve for {type_}")
            # 4. construct implicitly
            elif is_root:
                instance_type = type_

            if not instance_type:
                # 5. default value
                if default is not inspect.Parameter.empty:
                    return default
                raise TypeError(f"Unable to construct {type_}")

            kwargs: dict[str, Any] = {}
            signature = inspect.signature(instance_type.__init__)
            for dep_name, dep_type in get_input_type_hints(
                instance_type.__init__  # type: ignore
            ).items():
                resolved = self.resolve(
                    dep_type, is_root=False, default=signature.parameters[dep_name].default
                )
                kwargs[dep_name] = resolved

            try:
                instance = instance_type(**kwargs)  # type: ignore
            except TypeError:
                _log.exception(f"unable to construct {instance_type} as {type_}")
                raise
            else:
                self._singletons[instance_type] = instance

        self._singletons[type_] = instance
        return instance


def map_dependencies(
    instances: dict[type[Any], Any], graph: Optional[dict[Any, list[Any]]] = None
) -> dict[Any, list[Any]]:
    if not graph:
        graph = defaultdict(list)

    for type_, instance in instances.items():
        if not isinstance(instance, Hashable):
            continue
        if instance in graph:
            continue

        deps: dict[type[Any], Any] = {}

        for dep_type in get_input_type_hints(type_.__init__).values():  # type: ignore
            dep = instances.get(dep_type)
            if dep:
                # Unwrap container types.
                for _keys, sub_dep in recursive_iter(dep):
                    deps[type(sub_dep)] = sub_dep

        graph[instance] = list(deps.values())
        map_dependencies(deps, graph)

    return graph


def list_dependencies_in_init_order(dep_map: dict[Any, list[Any]]) -> list[list[Any]]:
    initialized: set[Any] = set()
    tiers = []
    while len(initialized) < len(dep_map):
        tier = []
        for instance, deps in dep_map.items():
            if instance in initialized:
                continue
            if all(dep in initialized for dep in deps):
                tier.append(instance)
                initialized.add(instance)
        if tier:
            tiers.append(tier)
    return tiers

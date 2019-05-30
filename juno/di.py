from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Hashable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any, Dict, List, Set, Type, TypeVar, Optional

from juno.utils import recursive_iter

from .typing import ExcType, ExcValue, Traceback, get_input_type_hints

T = TypeVar('T')


# All deps are handled as singleton. For transient lifetime, additional impl is required.
# Only type based resolution is applied. For name/type resolution, additional impl is required.
# If type registering was purely explicit, we could start using `resolve` after `__aenter__`.
class Container:

    def __init__(self) -> None:
        self._singletons: Dict[Type[Any], Any] = {}
        self._exit_stack = AsyncExitStack()

    async def __aenter__(self) -> Container:
        await self._exit_stack.__aenter__()
        dep_map = map_dependencies(self._singletons)
        for deps in list_dependencies_in_init_order(dep_map):
            await asyncio.gather(*(self._exit_stack.enter_async_context(d) for d in deps
                                 if isinstance(d, AbstractAsyncContextManager)))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await self._exit_stack.__aexit__(exc_type, exc, tb)

    def add_singleton(self, type_: Type[Any], obj: Any) -> None:
        self._singletons[type_] = obj

    def resolve(self, type_: Type[T]) -> T:
        kwargs = {}
        for dep_name, dep_type in get_input_type_hints(type_.__init__).items():
            kwargs[dep_name] = self._resolve_dep(dep_type)
        return type_(**kwargs)  # type: ignore

    def _resolve_dep(self, type_: type) -> Any:
        instance = self._singletons.get(type_)
        if not instance:
            kwargs = {}
            for dep_name, dep_type in get_input_type_hints(
                    type_.__init__).items():  # type: ignore
                kwargs[dep_name] = self._resolve_dep(dep_type)
            instance = type_(**kwargs)
            self._singletons[type_] = instance
        return instance


def map_dependencies(instances: Dict[Type[Any], Any], graph: Optional[Dict[Any, List[Any]]] = None
                     ) -> Dict[Any, List[Any]]:
    if not graph:
        graph = defaultdict(list)

    for type_, instance in instances.items():
        if not isinstance(instance, Hashable):
            continue
        if instance in graph:
            continue

        deps: Dict[Type[Any], Any] = {}

        for dep_type in get_input_type_hints(type_.__init__).values():  # type: ignore
            dep = instances.get(dep_type)
            if dep:
                # Unwrap container types.
                for _keys, sub_dep in recursive_iter(dep):
                    deps[type(sub_dep)] = sub_dep

        graph[instance] = list(deps.values())
        map_dependencies(deps, graph)

    return graph


def list_dependencies_in_init_order(dep_map: Dict[Any, List[Any]]) -> List[List[Any]]:
    initialized: Set[Any] = set()
    tiers = []
    while len(initialized) < len(dep_map):
        tier = []
        for instance, deps in dep_map.items():
            if instance in initialized:
                continue
            if all((dep in initialized for dep in deps)):
                tier.append(instance)
                initialized.add(instance)
        if tier:
            tiers.append(tier)
    return tiers

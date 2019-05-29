from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any, Dict, List, Set, Type, TypeVar

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
        dep_map = _map_dependencies(list(self._singletons.values()))
        for deps in _list_deps_in_init_order(dep_map):
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


def _map_dependencies(instances: List[Any]) -> Dict[Any, List[Any]]:
    graph: Dict[Any, List[Any]] = defaultdict(list)

    def fill_graph(instances: List[Any]) -> None:
        for instance in instances:
            if instance in graph:
                continue

            deps: List[Any] = []

            for t in get_input_type_hints(type(instance).__init__).values():  # type: ignore
                # Unwrap container types.
                origin = getattr(t, '__origin__', None)
                if origin is list:
                    t = t.__args__[0]  # type: ignore
                dep = [i for i in instances if type(i) is t]
                if len(dep) > 1:
                    raise Exception()
                if dep:
                    deps.append(dep[0])

            graph[instance] = deps
            fill_graph(deps)

    fill_graph(instances)
    return graph


def _list_deps_in_init_order(dep_map: Dict[Any, List[Any]]) -> List[List[Any]]:
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

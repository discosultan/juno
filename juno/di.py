from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Hashable
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar

from juno.utils import recursive_iter

from .typing import ExcType, ExcValue, Traceback, get_input_type_hints

T = TypeVar('T')

_log = logging.getLogger(__name__)


# All deps are handled as singleton. For transient lifetime, additional impl is required.
# Only type based resolution is applied. For name/type resolution, additional impl is required.
# If type registering was purely explicit, we could start using `resolve` after `__aenter__`.
class Container:
    def __init__(self) -> None:
        self._singleton_instances: Dict[Type[Any], Callable[[], Any]] = {}
        self._singleton_types: Dict[Type[Any], Callable[[], Type[Any]]] = {}
        self._singletons: Dict[Type[Any], Any] = {}

    async def __aenter__(self) -> Container:
        _log.info(f'created instances: {[i for i in self._singletons.values()]}')
        for deps in list_dependencies_in_init_order(map_dependencies(self._singletons)):
            await asyncio.gather(*(d.__aenter__() for d in deps if getattr(d, '__aenter__', None)))
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        for deps in reversed(list_dependencies_in_init_order(map_dependencies(self._singletons))):
            await asyncio.gather(
                *(d.__aexit__(exc_type, exc, tb) for d in deps if getattr(d, '__aexit__', None))
            )

    def add_singleton_instance(self, type_: Type[Any], factory: Callable[[], Any]) -> None:
        self._singleton_instances[type_] = factory

    def add_singleton_type(self, type_: Type[Any], factory: Callable[[], Type[Any]]) -> None:
        self._singleton_types[type_] = factory

    def resolve(self, type_: Type[T]) -> T:
        resolved = self._resolve(type_, raise_on_type_error=True)
        assert resolved
        return resolved

    def _resolve(self, type_: Type[T], raise_on_type_error: bool) -> Optional[T]:
        instance = self._singletons.get(type_)
        if instance:
            return instance

        instance_factory = self._singleton_instances.get(type_)
        if instance_factory:
            instance = instance_factory()
        else:
            instance_type = type_
            type_factory = self._singleton_types.get(type_)
            if type_factory:
                instance_type = type_factory()

            kwargs: Dict[str, Any] = {}
            for dep_name, dep_type in get_input_type_hints(instance_type.__init__  # type: ignore
                                                           ).items():
                resolved = self._resolve(dep_type, raise_on_type_error=False)
                if resolved is not None:
                    kwargs[dep_name] = resolved

            try:
                instance = instance_type(**kwargs)  # type: ignore
            except TypeError:
                if raise_on_type_error:
                    _log.exception(f'unable to construct {instance_type} as {type_}')
                    raise
                return None
            else:
                self._singletons[instance_type] = instance

        self._singletons[type_] = instance
        return instance


def map_dependencies(
    instances: Dict[Type[Any], Any], graph: Optional[Dict[Any, List[Any]]] = None
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

import inspect
import os
import sys
from dataclasses import is_dataclass
from enum import Enum
from types import ModuleType
from typing import Any, Mapping, Optional, TypeVar, Union, get_args, get_origin, get_type_hints

from juno import Interval, Timestamp, json
from juno.itertools import recursive_iter
from juno.time import strfinterval, strftimestamp, strpinterval, strptimestamp
from juno.typing import TypeConstructor, get_input_type_hints, isenum, isnamedtuple
from juno.utils import get_module_type, map_concrete_module_types

T = TypeVar("T")


def from_env(
    env: Mapping[str, str] = os.environ, prefix: str = "JUNO", separator: str = "__"
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    entries = (
        (k.split(separator)[1:], v) for k, v in env.items() if k.startswith(prefix + separator)
    )
    for keys, value in entries:
        typed_keys = [int(k) if str.isdigit(k) else k.lower() for k in keys]
        target: dict[Any, Any] = result
        for i in range(len(typed_keys)):
            k1 = typed_keys[i]
            k2 = typed_keys[i + 1] if i < len(typed_keys) - 1 else None
            if k2 is None:
                target[k1] = value
            else:
                if isinstance(k2, int):
                    target[k1] = _ensure_list(_get(target, k1), k2 + 1)
                else:
                    target[k1] = _ensure_dict(_get(target, k1))
                target = target[k1]
    return result


def from_json_file(file: str) -> dict[str, Any]:
    with open(file, "r") as f:
        return json.load(f)


def list_names(config: dict[str, Any], name: str) -> set[str]:
    result = set()
    name_plural = name + "s"
    for keys, v in recursive_iter(config):
        # Check for key value: `exchange: "binance"`.
        last_key = keys[-1]
        if isinstance(last_key, str) and _matches_name(last_key, name):
            result.add(v)
        # Check for key list: `exchanges: ["binance", "coinbase"]`
        elif len(keys) >= 2:
            second_to_last_key = keys[-2]
            if isinstance(second_to_last_key, str) and _matches_name(
                second_to_last_key, name_plural
            ):
                result.add(v)
    return result


def _matches_name(key: str, name: str) -> bool:
    return key.split("_")[-1] == name


def _ensure_list(existing: Optional[list[Any]], length: int) -> list[Any]:
    if existing is None:
        return [None] * length
    if len(existing) < length:
        return existing + [None] * (length - len(existing))
    return existing


def _ensure_dict(existing: Optional[dict[str, Any]]) -> dict[str, Any]:
    if existing is None:
        return {}
    return existing


def _get(collection: Any, key: Any) -> Optional[Any]:
    if isinstance(collection, list):
        return collection[key]
    else:
        return collection.get(key)


def init_instances_mentioned_in_config(type_: type, config: dict[str, Any]) -> list[Any]:
    result = []
    name = type_.__name__.lower()
    module_types = _map_type_parent_module_types(type_)
    for name in list_names(config, name):
        type_ = module_types[name]
        if not inspect.isabstract(type_):
            result.append(init_instance(type_, config))
    return result


def try_init_all_instances(type_: type, config: dict[str, Any]) -> list[Any]:
    result = []
    for type_ in _map_type_parent_module_types(type_).values():
        if inspect.isabstract(type_):
            continue
        try:
            result.append(init_instance(type_, config))
        except TypeError:
            pass
    return result


def init_module_instance(module: ModuleType, config: dict[str, Any]) -> Any:
    type_name = config.get("type")
    if not type_name:
        raise ValueError('Unable to init module instance. Property "type" missing in config')
    type_ = get_module_type(module, type_name)
    return init_instance(type_, config)


def get_module_type_constructor(
    module: ModuleType, config: dict[str, Any]
) -> TypeConstructor[Any]:
    type_, kwargs = get_module_type_and_kwargs(module, config)
    return TypeConstructor.from_type(type_, **kwargs)


def get_type_name_and_kwargs(config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    type_name = config.get("type")
    if not type_name:
        raise ValueError('Unable to get type name. Property "type" missing in config')
    return type_name, {k: v for k, v in config.items() if k != "type"}


def get_module_type_and_kwargs(
    module: ModuleType, config: dict[str, Any]
) -> tuple[type, dict[str, Any]]:
    type_name = config.get("type")
    if not type_name:
        raise ValueError('Unable to get module type. Property "type" missing in config')
    type_ = get_module_type(module, type_name)
    return type_, kwargs_for(type_.__init__, config)


# TODO: Cannot make generic because https://github.com/python/mypy/issues/5374
def init_instance(type_: type[Any], config: dict[str, Any]) -> Any:
    # Supports loading abstract types by resolving concrete type from config.
    if inspect.isabstract(type_):
        type_ = resolve_concrete(type_, config)

    # Supports passing either root config or type specific config. See if we can dig deeper based
    # on type name.
    sub_config = config.get(type_.__name__.lower())
    if sub_config:
        config = sub_config

    signature = type_ if isnamedtuple(type_) else type_.__init__
    return type_(**kwargs_for(signature, config))  # type: ignore


def kwargs_for(signature: Any, config: dict[str, Any]) -> dict[str, Any]:
    parsed_config = {}
    for k, t in get_input_type_hints(signature).items():
        if (config_val := config.get(k, "__missing__")) != "__missing__":
            parsed_config[k] = config_to_type(config_val, t)
    return parsed_config


def config_to_type(value: Any, type_: Any) -> Any:
    # Aliases.
    if type_ is Any:
        return value
    if type_ is Interval:
        return strpinterval(value)
    if type_ is Timestamp:
        return strptimestamp(value)

    origin = get_origin(type_)
    if origin:
        if origin is Union:  # Most probably Optional[T].
            st, _ = get_args(type_)
            return config_to_type(value, st) if value is not None else None
        if origin is type:  # typing.type[T]
            raise NotImplementedError()
        if origin is list:  # typing.list[T]
            (st,) = get_args(type_)
            return [config_to_type(sv, st) for sv in value]
        if origin is dict:  # typing.dict[T, Y]
            skt, svt = get_args(type_)
            return {config_to_type(sk, skt): config_to_type(sv, svt) for sk, sv in value.items()}

    if isenum(type_):
        return type_[value.upper()]
    if isnamedtuple(type_):
        type_hints = get_type_hints(type_)
        return type_(
            **{sn: config_to_type(value[sn], st) for sn, st in type_hints.items() if sn in value}
        )

    return value


def type_to_config(value: Any, type_: Any) -> Any:
    # Aliases.
    if type_ is Any:
        return value
    if type_ is Interval:
        return strfinterval(value)
    if type_ is Timestamp:
        return strftimestamp(value)

    origin = get_origin(type_)
    if origin:
        if origin is Union:  # Most probably Optional[T].
            st, _ = get_args(type_)
            return type_to_config(value, st) if value is not None else None
        if origin is type:  # typing.type[T]
            return value.__name__.lower()
        if origin is list:  # typing.list[T]
            (st,) = get_args(type_)
            return [type_to_config(sv, st) for sv in value]
        if origin is dict:  # typing.dict[T, Y]
            skt, svt = get_args(type_)
            return {type_to_config(sk, skt): type_to_config(sv, svt) for sk, sv in value.items()}

    if inspect.isclass(type_) and issubclass(type_, Enum):
        return value.name.lower()
    if isnamedtuple(type_) or is_dataclass(type_):
        type_hints = get_type_hints(type_)
        return {sn: type_to_config(getattr(value, sn), st) for sn, st in type_hints.items()}

    return value


def resolve_concrete(
    type_: type[Any], config: dict[str, Any], default: Any = inspect.Parameter.empty
) -> type[Any]:
    if not inspect.isabstract(type_):
        raise ValueError(f"Unable to resolve concrete type for a non-abstract type {type_}")

    abstract_name = type_.__name__.lower()
    concrete_name = config.get(abstract_name)
    if not concrete_name:
        if default is inspect.Parameter.empty:
            raise ValueError(f"Concrete name not found for {abstract_name} in config")
        return default

    module_type_map = _map_type_parent_module_types(type_)
    concrete_type = module_type_map.get(concrete_name)
    if not concrete_type:
        if default is inspect.Parameter.empty:
            raise ValueError(f"Concrete type {concrete_name} not found")
        return default

    return concrete_type


def _map_type_parent_module_types(type_: type[Any]) -> dict[str, type[Any]]:
    module_name = type_.__module__
    parent_module_name = module_name[0 : module_name.rfind(".")]
    return map_concrete_module_types(sys.modules[parent_module_name])


def format_as_config(obj: Any) -> str:
    cfg = type_to_config(obj, type(obj))
    return json.dumps(cfg, indent=4)

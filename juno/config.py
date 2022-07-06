import inspect
import os
from types import ModuleType
from typing import Any, Mapping, Optional

from juno import serialization
from juno.inspect import (
    GenericConstructor,
    get_module_type,
    isnamedtuple,
    map_type_parent_module_types,
)
from juno.itertools import recursive_iter
from juno.path import load_json_file, load_yaml_file
from juno.typing import get_input_type_hints


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
    return load_json_file(file)


def from_yaml_file(file: str) -> dict[str, Any]:
    return load_yaml_file(file)


def from_file(file: str) -> dict[str, Any]:
    file_lower = file.lower()
    if file_lower.endswith("json"):
        return from_json_file(file)
    elif file_lower.endswith("yaml") or file_lower.endswith("yml"):
        return from_yaml_file(file)
    else:
        raise ValueError("Invalid config file. Expected JSON or YAML format")


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
    type_name = type_.__name__.lower()
    module_types = map_type_parent_module_types(type_)
    for name in list_names(config, type_name):
        type_ = module_types[name]
        if not inspect.isabstract(type_):
            result.append(init_instance(type_, config))
    return result


def try_init_all_instances(type_: type, config: dict[str, Any]) -> list[Any]:
    result = []
    for parent_type in map_type_parent_module_types(type_).values():
        if inspect.isabstract(parent_type):
            continue
        try:
            result.append(init_instance(parent_type, config))
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
) -> GenericConstructor[Any]:
    type_, kwargs = get_module_type_and_kwargs(module, config)
    return GenericConstructor.from_type(type_, **kwargs)


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
            parsed_config[k] = serialization.config.deserialize(config_val, t)
    return parsed_config


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

    module_type_map = map_type_parent_module_types(type_)
    concrete_type = module_type_map.get(concrete_name)
    if not concrete_type:
        if default is inspect.Parameter.empty:
            raise ValueError(f"Concrete type {concrete_name} not found")
        return default

    return concrete_type

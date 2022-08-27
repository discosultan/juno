from collections import deque
from dataclasses import is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional, get_args, get_type_hints

from typing_inspect import (
    get_parameters,
    is_generic_type,
    is_optional_type,
    is_typevar,
    is_union_type,
)

from juno.inspect import (
    get_fully_qualified_name,
    get_type_by_fully_qualified_name,
    isenum,
    isnamedtuple,
    istypeddict,
)
from juno.typing import get_root_origin


def deserialize(value: Any, type_: Any) -> Any:
    tagged_type = (
        get_type_by_fully_qualified_name(vt)
        if isinstance(value, dict) and (vt := value.get("__type__"))
        else None
    )
    origin_type = get_root_origin(type_)
    resolved_type = tagged_type or origin_type or type_

    if resolved_type is Any:
        return value

    if resolved_type is type(None):  # noqa: E721
        if value is not None:
            raise TypeError(f"Incorrect {value=} for {type_=}")
        return None

    if is_union_type(resolved_type):
        if is_optional_type(type_) and value is None:
            return None

        resolved = "__missing__"
        for arg in get_args(type_):
            try:
                resolved = deserialize(value, arg)
            except TypeError:
                pass
        if resolved == "__missing__":
            raise TypeError(f"Incorrect {value=} for {type_=}")
        return resolved

    if isenum(resolved_type):
        return type_(value)

    # Needs to be a list because type_ can be non-hashable for lookup in a set.
    if resolved_type in [bool, int, float, str, Decimal]:
        return value

    if resolved_type is list:
        (sub_type,) = get_args(type_)
        for i, sub_value in enumerate(value):
            value[i] = deserialize(sub_value, sub_type)
        return value

    if resolved_type is deque:
        (sub_type,) = get_args(type_)
        return deque((deserialize(sv, sub_type) for sv in value), maxlen=len(value))

    if isnamedtuple(resolved_type):
        annotations = get_type_hints(type_)
        args = []
        for i, (_name, sub_type) in enumerate(annotations.items()):
            if i >= len(value):
                # Resort to default values.
                break
            sub_value = value[i]
            args.append(deserialize(sub_value, sub_type))
        return type_(*args)

    if resolved_type is tuple:
        sub_types = get_args(type_)
        # Handle ellipsis. special case. I.e `tuple[int, ...]`.
        if len(sub_types) == 2 and sub_types[1] is Ellipsis:
            sub_type = sub_types[0]
            return tuple(deserialize(sv, sub_type) for sv in value)
        # Handle regular cases. I.e `tuple[int, str, float]`.
        else:
            return tuple(deserialize(sv, st) for sv, st in zip(value, sub_types))

    if istypeddict(resolved_type):
        annotations = get_type_hints(resolved_type)
        return {key: deserialize(sub_value, annotations[key]) for key, sub_value in value.items()}

    if resolved_type is dict:
        _, sub_type = get_args(type_)
        return {key: deserialize(sub_value, sub_type) for key, sub_value in value.items()}

    if resolved_type is Literal:
        return value

    annotations = get_type_hints(resolved_type)
    type_args_map = {p: a for p, a in zip(get_parameters(resolved_type), get_args(type_))}
    kwargs = {}
    for name, sub_type in ((k, v) for k, v in annotations.items() if k in annotations):
        if name not in value:
            continue
        # Substitute generics.
        # TODO: Generalize
        if is_typevar(sub_type):
            sub_type = type_args_map[sub_type]
        if is_optional_type(sub_type):
            sub_type_args = get_args(sub_type)[0:-1]  # Discard None.
            sub_type_arg = sub_type_args[0]
            if is_typevar(sub_type_arg):
                sub_type = Optional[type_args_map[sub_type_arg]]
        if is_generic_type(sub_type):
            sub_type_args = get_args(sub_type)
            if len(sub_type_args) == 1 and is_typevar(sub_type_args[0]):
                sub_type = sub_type[type_args_map[sub_type_args[0]]]
        sub_value = value[name]
        kwargs[name] = deserialize(sub_value, sub_type)

    if is_dataclass(resolved_type):
        return resolved_type(**kwargs)
    else:
        instance = resolved_type.__new__(resolved_type)  # type: ignore
        for k, v in kwargs.items():
            setattr(instance, k, v)
        return instance


def serialize(value: Any, type_: Any = None) -> Any:
    if type_ is None:
        type_ = type(value)

    if value is None:
        return value

    if isinstance(value, (bool, int, float, str, Decimal)):
        return value

    # Also includes NamedTuple.
    if isinstance(value, (list, tuple, deque)):
        return list(map(serialize, value))

    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}

    if isinstance(value, Enum):
        return value.value

    # Data class and regular class. We don't want to use `dataclasses.asdict` because it is
    # recursive in converting dataclasses.
    if (value_dict := getattr(value, "__dict__", None)) is not None:
        res = {k: serialize(v) for k, v in value_dict.items()}
        res["__type__"] = get_fully_qualified_name(type_)
        return res

    raise NotImplementedError(f"Unable to convert {value}")

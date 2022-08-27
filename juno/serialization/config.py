from dataclasses import is_dataclass
from types import NoneType
from typing import Any, Union, get_args, get_origin, get_type_hints

from juno import Interval, Interval_, Timestamp, Timestamp_
from juno.inspect import isenum, isnamedtuple, istypeddict


def deserialize(value: Any, type_: Any) -> Any:
    # Aliases.
    if type_ is Any:
        return value
    if type_ is Interval:
        return Interval_.parse(value)
    if type_ is Timestamp:
        return Timestamp_.parse(value)
    if type_ is NoneType:
        if value is None:
            return None
        raise TypeError(f"Invalid value {value} for NoneType")

    origin = get_origin(type_)
    if origin:
        # Either Union[T, Y] or Optional[T].
        # Optional[T] is equivalent to Union[T, NoneType].
        if origin is Union:
            for arg in get_args(type_):
                try:
                    return deserialize(value, arg)
                except Exception:
                    pass
            raise TypeError(f"Unable to deserialize value {value} of type {type_}")
        if origin is type:  # typing.type[T]
            raise NotImplementedError()
        if origin is list:  # typing.list[T]
            (st,) = get_args(type_)
            return [deserialize(sv, st) for sv in value]
        if origin is tuple:
            sub_types = get_args(type_)
            # Handle ellipsis. special case. I.e `tuple[int, ...]`.
            if len(sub_types) == 2 and sub_types[1] is Ellipsis:
                sub_type = sub_types[0]
                return tuple(deserialize(sv, sub_type) for sv in value)
            # Handle regular cases. I.e `tuple[int, str, float]`.
            else:
                return tuple(deserialize(sv, st) for sv, st in zip(value, sub_types))
        if origin is dict:  # typing.dict[T, Y]
            skt, svt = get_args(type_)
            return {deserialize(sk, skt): deserialize(sv, svt) for sk, sv in value.items()}

    if isenum(type_):
        return type_[value.upper()]
    if isnamedtuple(type_):
        type_hints = get_type_hints(type_)
        return type_(
            *(
                deserialize(sub_value, sub_type)
                for sub_value, sub_type in zip(value, type_hints.values())
            )
        )
    if is_dataclass(type_):
        type_hints = get_type_hints(type_)
        return type_(
            **{sn: deserialize(value[sn], st) for sn, st in type_hints.items() if sn in value}
        )
    if istypeddict(type_):
        annotations = get_type_hints(type_)
        return type_(
            **{key: deserialize(sub_value, annotations[key]) for key, sub_value in value.items()}
        )

    return value


def serialize(value: Any, type_: Any = None) -> Any:
    if type_ is None:
        type_ = type(value)

    # Aliases.
    if type_ is Any:
        return value
    if type_ is Interval:
        return Interval_.format(value)
    if type_ is Timestamp:
        return Timestamp_.format(value)
    if type_ is NoneType:
        if value is None:
            return None
        raise TypeError(f"Invalid value {value} for NoneType")

    origin = get_origin(type_)
    if origin:
        # Either Union[T, Y] or Optional[T].
        # Optional[T] is equivalent to Union[T, NoneType].
        if origin is Union:
            for arg in get_args(type_):
                try:
                    return serialize(value, arg)
                except Exception:
                    pass
            raise TypeError(f"Unable to serialize value {value} of type {type_}")
        if origin is type:  # typing.type[T]
            return value.__name__.lower()
        if origin is list:  # typing.list[T]
            (st,) = get_args(type_)
            return [serialize(sv, st) for sv in value]
        if origin is tuple:
            sub_types = get_args(type_)
            # Handle ellipsis. special case. I.e `tuple[int, ...]`.
            if len(sub_types) == 2 and sub_types[1] is Ellipsis:
                sub_type = sub_types[0]
                return [serialize(sv, sub_type) for sv in value]
            # Handle regular cases. I.e `tuple[int, str, float]`.
            else:
                return [serialize(sv, st) for sv, st in zip(value, sub_types)]
        if origin is dict:  # typing.dict[T, Y]
            skt, svt = get_args(type_)
            return {serialize(sk, skt): serialize(sv, svt) for sk, sv in value.items()}

    if isenum(type_):
        return value.name.lower()
    if isnamedtuple(type_):
        type_hints = get_type_hints(type_)
        return [serialize(getattr(value, sn), st) for sn, st in type_hints.items()]
    if is_dataclass(type_):
        type_hints = get_type_hints(type_)
        return {sn: serialize(getattr(value, sn), st) for sn, st in type_hints.items()}
    if istypeddict(type_):
        annotations = get_type_hints(type_)
        return {key: serialize(sub_value, annotations[key]) for key, sub_value in value.items()}

    return value

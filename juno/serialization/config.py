import inspect
from dataclasses import is_dataclass
from enum import Enum
from types import NoneType
from typing import Any, Union, get_args, get_origin, get_type_hints

from juno import Interval, Timestamp
from juno.inspect import isenum, isnamedtuple
from juno.time import strfinterval, strftimestamp, strpinterval, strptimestamp


def deserialize(value: Any, type_: Any) -> Any:
    # Aliases.
    if type_ is Any:
        return value
    if type_ is Interval:
        return strpinterval(value)
    if type_ is Timestamp:
        return strptimestamp(value)
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
        if origin is dict:  # typing.dict[T, Y]
            skt, svt = get_args(type_)
            return {deserialize(sk, skt): deserialize(sv, svt) for sk, sv in value.items()}

    if isenum(type_):
        return type_[value.upper()]
    if isnamedtuple(type_) or is_dataclass(type_):
        type_hints = get_type_hints(type_)
        return type_(
            **{sn: deserialize(value[sn], st) for sn, st in type_hints.items() if sn in value}
        )

    return value


def serialize(value: Any, type_: Any = None) -> Any:
    if type_ is None:
        type_ = type(value)

    # Aliases.
    if type_ is Any:
        return value
    if type_ is Interval:
        return strfinterval(value)
    if type_ is Timestamp:
        return strftimestamp(value)
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
        if origin is dict:  # typing.dict[T, Y]
            skt, svt = get_args(type_)
            return {serialize(sk, skt): serialize(sv, svt) for sk, sv in value.items()}

    if inspect.isclass(type_) and issubclass(type_, Enum):
        return value.name.lower()
    if isnamedtuple(type_) or is_dataclass(type_):
        type_hints = get_type_hints(type_)
        return {sn: serialize(getattr(value, sn), st) for sn, st in type_hints.items()}

    return value

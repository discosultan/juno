from typing import NamedTuple

import pytest
from tenacity import RetryError, retry

from juno.tenacity import stop_after_attempt_with_reset

from .fakes import Time


class CustomException(Exception):
    pass


class RaiseException(NamedTuple):
    value: Exception


class SetTime(NamedTuple):
    value: int


def test_stop_after_attempt_with_reset_failure_before_reset() -> None:
    @retry(stop=stop_after_attempt_with_reset(max_attempt_number=3, time_to_reset=1.0))
    def target() -> None:
        raise CustomException()

    with pytest.raises(RetryError):
        target()

    assert target.retry.statistics["attempt_number"] == 3  # type: ignore


def test_stop_after_attempt_with_reset_success() -> None:
    time = Time(time=0)
    steps = [
        RaiseException(CustomException()),
        RaiseException(CustomException()),
        SetTime(2),
        RaiseException(CustomException()),
        RaiseException(CustomException()),
    ]

    @retry(
        stop=stop_after_attempt_with_reset(
            max_attempt_number=3,
            time_to_reset=1.0,
            get_time=time.get_time,
        ),
    )
    def target() -> None:
        while len(steps) > 0:
            step = steps.pop(0)
            if isinstance(step, RaiseException):
                raise step.value
            elif isinstance(step, SetTime):
                time.time = step.value

    target()

    assert target.retry.statistics["attempt_number"] == 5  # type: ignore


def test_stop_after_attempt_with_reset_failure_after_reset() -> None:
    time = Time(time=0)
    steps = [
        RaiseException(CustomException()),
        RaiseException(CustomException()),
        SetTime(2),
        RaiseException(CustomException()),
        RaiseException(CustomException()),
        RaiseException(CustomException()),
    ]

    @retry(
        stop=stop_after_attempt_with_reset(
            max_attempt_number=3,
            time_to_reset=1.0,
            get_time=time.get_time,
        ),
    )
    def target() -> None:
        while len(steps) > 0:
            step = steps.pop(0)
            if isinstance(step, RaiseException):
                raise step.value
            elif isinstance(step, SetTime):
                time.time = step.value

    with pytest.raises(RetryError):
        target()

    assert target.retry.statistics["attempt_number"] == 5  # type: ignore

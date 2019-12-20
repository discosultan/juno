import pytest
from tenacity import RetryError, retry

from juno.tenacity import stop_after_attempt_with_reset

from .fakes import Time


class CustomException(Exception):
    pass


def test_stop_after_attempt_with_reset_failure_before_reset():
    @retry(stop=stop_after_attempt_with_reset(max_attempt_number=3, time_to_reset=1.0))
    def target():
        raise CustomException()

    with pytest.raises(RetryError):
        target()

    assert target.retry.statistics['attempt_number'] == 3


def test_stop_after_attempt_with_reset_success():
    time = Time(time=0)
    steps = [
        ('raise', CustomException()),
        ('raise', CustomException()),
        ('time', 2),
        ('raise', CustomException()),
        ('raise', CustomException()),
    ]

    @retry(stop=stop_after_attempt_with_reset(
        max_attempt_number=3, time_to_reset=1.0, get_time=time.get_time)
    )
    def target():
        while len(steps) > 0:
            action, value = steps.pop(0)
            if action == 'raise':
                raise value
            elif action == 'time':
                time.time = value

    target()

    assert target.retry.statistics['attempt_number'] == 5


def test_stop_after_attempt_with_reset_failure_after_reset():
    time = Time(time=0)
    steps = [
        ('raise', CustomException()),
        ('raise', CustomException()),
        ('time', 2),
        ('raise', CustomException()),
        ('raise', CustomException()),
        ('raise', CustomException()),
    ]

    @retry(stop=stop_after_attempt_with_reset(
        max_attempt_number=3, time_to_reset=1.0, get_time=time.get_time)
    )
    def target():
        while len(steps) > 0:
            action, value = steps.pop(0)
            if action == 'raise':
                raise value
            elif action == 'time':
                time.time = value

    with pytest.raises(RetryError):
        target()

    assert target.retry.statistics['attempt_number'] == 5

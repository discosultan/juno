import pytest

from juno.config import from_env


@pytest.fixture(scope='session')
def config():
    return from_env()

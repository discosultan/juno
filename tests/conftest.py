import pytest

from juno.config import load_from_env


@pytest.fixture(scope='session')
def config():
    return load_from_env()

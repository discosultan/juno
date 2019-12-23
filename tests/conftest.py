import pytest

from juno.config import config_from_env


@pytest.fixture(scope='session')
def config():
    return config_from_env()

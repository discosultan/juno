import pytest

import juno


@pytest.fixture(scope='session')
def config():
    return juno.config.from_env()

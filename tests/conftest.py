import pytest

import juno

from . import fakes


@pytest.fixture(scope='session')
def config():
    return juno.config.from_env()


@pytest.fixture
async def storage(loop):
    async with fakes.Storage() as storage:
        yield storage

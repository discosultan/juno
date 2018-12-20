import logging


_log = logging.getLogger(__package__)


class Orderbook:

    def __init____(self, services, config):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

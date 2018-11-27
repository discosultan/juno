import aiohttp


# Adds logging to aiohttp client session.
# https://stackoverflow.com/a/45590516/1466456
# Note that aiohttp client session is not meant to be extended.
# https://github.com/aio-libs/aiohttp/issues/3185
class ClientSession:

    logger = logging.getLogger('aiohttp.client')

    def __init__(self, *args, **kwargs):
        self._session = aiohttp.ClientSession(*args, **kwargs)

    async def __aenter__(self):
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def request(self, method, url, **kwargs):
        self.logger.info(f'{method} {url}')
        self.logger.debug(kwargs)
        async with self._session.request(method, url, **kwargs) as res:
            self.logger.info(f'{res.status} {res.reason}')
            if res.status >= 400:
                self.logger.error(await res.text())
                res.raise_for_status()
            else:
                self.logger.debug(await res.text())
            yield res

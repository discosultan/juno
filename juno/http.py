from contextlib import asynccontextmanager
import logging

import aiohttp


# Adds logging to aiohttp client session.
# https://stackoverflow.com/a/45590516/1466456
# Note that aiohttp client session is not meant to be extended.
# https://github.com/aio-libs/aiohttp/issues/3185
class ClientSession:

    _log = logging.getLogger('aiohttp.client')

    def __init__(self, *args, **kwargs):
        self._raise_for_status = kwargs.get('raise_for_status')
        kwargs.pop('raise_for_status')
        self._session = aiohttp.ClientSession(*args, **kwargs)

    async def __aenter__(self):
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def request(self, method, url, **kwargs):
        self._log.info(f'{method} {url}')
        self._log.debug(kwargs)
        async with self._session.request(method, url, **kwargs) as res:
            self._log.info(f'{res.status} {res.reason}')
            if res.status >= 400:
                self._log.error(await res.text())
                if self._raise_for_status:
                    res.raise_for_status()
            else:
                self._log.debug(await res.text())
            yield res

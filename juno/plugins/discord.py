from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import aiohttp
import simplejson as json

from juno.agents import Agent
from juno.agents.summary import Position, TradingSummary
from juno.http import ClientSession, ClientWebSocketResponse
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import LeakyBucket, retry_on

# Information about Discord lifetime op codes:
# https://discordapp.com/developers/docs/topics/opcodes-and-status-codes

_BASE_URL = 'https://discordapp.com/api/v6'

_log = logging.getLogger(__name__)


class Discord:

    attach_to = ['backtest']

    @staticmethod
    @asynccontextmanager
    async def activate(agent: Agent, config: Dict[str, Any]) -> AsyncIterator[None]:
        ee = agent.ee

        async with Discord(config) as client:

            @ee.on('pos_opened')
            async def on_position_opened(pos: Position) -> None:
                asyncio.get_running_loop().create_task(
                    client.post_msg(f'Opened a position:\n```\n{pos}\n```'))

            @ee.on('pos_closed')
            async def on_position_closed(pos: Position) -> None:
                asyncio.get_running_loop().create_task(
                    client.post_msg(f'Closed a position:\n```\n{pos}\n```'))

            @ee.on('summary')
            async def on_summary(summary: TradingSummary) -> None:
                asyncio.get_running_loop().create_task(
                    client.post_msg(f'Trading summary:\n```\n{summary}\n```'))

            # @ee.on('img_saved')
            # async def on_image_saved(path: str) -> None:
            #     asyncio.get_running_loop().create_task(
            #         client.post_img(path))

            asyncio.create_task(client.run())
            yield

    def __init__(self, config: Dict[str, Any]) -> None:
        self._token = config['token']
        self._channel_id = config['channel_id']

    async def __aenter__(self) -> Discord:
        self._last_sequence: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._session = ClientSession(headers={'Authorization': f'Bot {self._token}'})
        self._limiter = LeakyBucket(rate=5, period=5)  # 5 per 5 seconds.
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    async def run(self) -> None:
        try:
            _log.info('starting')
            url = (await self._request('GET', '/gateway'))['url']

            while True:
                async with self._ws_connect(f'{url}?v=6&encoding=json') as ws:
                    async for msg in ws:
                        if msg.type is aiohttp.WSMsgType.CLOSED:
                            _log.error(f'websocket connection closed unexpectedly ({msg})')
                            break

                        data = json.loads(msg.data)

                        if data['op'] == 0:  # Dispatch.
                            if data['t'] == 'READY':
                                _log.info('ready')
                            if self._last_sequence.done():
                                self._last_sequence = asyncio.get_running_loop().create_future()
                            self._last_sequence.set_result(data['d'])
                        elif data['op'] == 10:  # Hello.
                            _log.info('hello from discord')
                            asyncio.get_running_loop().create_task(
                                self._heartbeat(ws, data['d']['heartbeat_interval']))
                            await ws.send_json({
                                'op': 2,  # Identify.
                                'd': {
                                    'token': self._token,
                                    'properties': {},
                                    'compress': False,
                                    'large_threshold': 250
                                }
                            })
                        elif data['op'] == 11:  # Heartbeat ACK.
                            _log.info('acknowledged heartbeat')
                        elif data['op'] >= 4000:
                            _log.error(f'gateway closed ({data})')
        except asyncio.CancelledError:
            _log.info('main task cancelled')
        except Exception as e:
            _log.error(f'unhandled error in main ({e})')

    async def post_msg(self, msg: Any) -> None:
        # TODO: wtf? # await self.ee.emit('discord_msg', msg)
        # Careful! Request is patched above. Make sure not to accidentally use post method.
        await self._request(
            'POST', f'/channels/{self._channel_id}/messages', json={'content': msg})

    async def post_img(self, path: str) -> None:
        data = {'file': open(path, 'rb')}
        await self._request('POST', f'/channels/{self._channel_id}/messages', data=data)

    async def _heartbeat(self, ws: ClientWebSocketResponse, interval: int) -> None:
        try:
            while True:
                await asyncio.sleep(interval / 1000)
                await ws.send_json({
                    'op': 1,  # Heartbeat.
                    'd': self._last_sequence.result()
                })
        except asyncio.CancelledError:
            _log.info('heartbeat task cancelled')
        except ConnectionResetError:
            _log.warning('heartbeat connection lost')
        except Exception as e:
            _log.error(f'unhandled error in heartbeat ({e})')

    @retry_on(aiohttp.ClientConnectionError, max_tries=3)
    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        await self._limiter.acquire(1)
        await self._last_sequence
        async with self._session.request(method, _BASE_URL + url, **kwargs) as res:
            return await res.json()

    @asynccontextmanager
    @retry_on(aiohttp.WSServerHandshakeError, max_tries=3)
    async def _ws_connect(self, url: str, **kwargs: Any) -> AsyncIterator[ClientWebSocketResponse]:
        async with self._session.ws_connect(url, **kwargs) as ws:
            yield ws

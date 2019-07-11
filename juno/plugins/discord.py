from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

import aiohttp
import simplejson as json

from juno.agents import Agent
from juno.agents.summary import Position
from juno.http import ClientSession, ClientWebSocketResponse
from juno.typing import ExcType, ExcValue, Traceback
from juno.utils import LeakyBucket, retry_on

# Information about Discord lifetime op codes:
# https://discordapp.com/developers/docs/topics/opcodes-and-status-codes

_BASE_URL = 'https://discordapp.com/api/v6'

_log = logging.getLogger(__name__)


@asynccontextmanager
async def activate(agent: Agent, plugin_config: Dict[str, Any]) -> AsyncIterator[None]:

    def format_action(action: str) -> str:
        return f'{type(agent).__name__} agent {agent.name} {action}.\n'

    def format_block(title: str, content: str) -> str:
        return f'{title}:\n```\n{content}\n```\n'

    async with Discord(
            token=plugin_config['token'],
            channel_id=plugin_config['channel_id'][type(agent).__name__.lower()]) as client:

        @agent.ee.on('starting')
        async def on_starting(agent_config: Dict[str, Any]) -> None:
            await client.post_msg(format_action('starting') +
                                  format_block('Config', str(agent_config)))

        @agent.ee.on('position_opened')
        async def on_position_opened(pos: Position) -> None:
            await client.post_msg(format_action('opened a position') +
                                  format_block('Position', str(pos)) +
                                  format_block('Summary', str(agent.result)))

        @agent.ee.on('position_closed')
        async def on_position_closed(pos: Position) -> None:
            await client.post_msg(format_action('closed a position') +
                                  format_block('Position', str(pos)) +
                                  format_block('Summary', str(agent.result)))

        @agent.ee.on('finished')
        async def on_finished() -> None:
            await client.post_msg(format_action('finished') +
                                  format_block('Summary', str(agent.result)))

        @agent.ee.on('errored')
        async def on_errored(_e: Exception) -> None:
            await client.post_msg(format_action('errored') +
                                  format_block('Exception', traceback.format_exc()) +
                                  format_block('Summary', str(agent.result)))

        yield


class Discord:

    def __init__(self, token: str, channel_id: str, timeout: float = 10.0) -> None:
        self._token = token
        self._channel_id = channel_id
        self._timeout = timeout

    async def __aenter__(self) -> Discord:
        self._last_sequence: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._session = ClientSession(headers={'Authorization': f'Bot {self._token}'})
        # TODO: At the time of writing the limit was 5 reqs per 5 seconds. They refresh
        # periodically though. The recommended approach is to limit based on headers returned.
        # See https://discordapp.com/developers/docs/topics/rate-limits
        self._limiter = LeakyBucket(rate=1, period=1)
        await self._session.__aenter__()
        self._run_task = asyncio.create_task(self._run())
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        self._run_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        await self._run_task
        if self._heartbeat_task:
            await self._heartbeat_task

        await self._session.__aexit__(exc_type, exc, tb)

    async def post_msg(self, msg: Any) -> None:
        # Careful! Request is patched above. Make sure not to accidentally use post method.
        await asyncio.wait_for(self._last_sequence, timeout=self._timeout)
        await self._request(
            'POST', f'/channels/{self._channel_id}/messages', json={'content': msg})

    async def post_img(self, path: str) -> None:
        await asyncio.wait_for(self._last_sequence, timeout=self._timeout)
        data = {'file': open(path, 'rb')}
        await self._request('POST', f'/channels/{self._channel_id}/messages', data=data)

    async def _run(self) -> None:
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
                            self._heartbeat_task = asyncio.create_task(
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
                            _log.debug('acknowledged heartbeat')
                        elif data['op'] >= 4000:
                            _log.error(f'gateway closed ({data})')
        except asyncio.CancelledError:
            _log.info('main task cancelled')
        except Exception:
            _log.exception('unhandled exception in main')

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
        except Exception:
            _log.exception('unhandled exception in heartbeat')

    @retry_on(aiohttp.ClientConnectionError, max_tries=3)
    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        await self._limiter.acquire(1)
        async with self._session.request(method, _BASE_URL + url, **kwargs) as res:
            return await res.json()

    @asynccontextmanager
    # @retry_on(aiohttp.WSServerHandshakeError, max_tries=3)
    async def _ws_connect(self, url: str, **kwargs: Any) -> AsyncIterator[ClientWebSocketResponse]:
        async with self._session.ws_connect(url, **kwargs) as ws:
            yield ws

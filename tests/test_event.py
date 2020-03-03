from juno.components import Event


async def test_event() -> None:
    event = Event()
    exc = Exception('Expected error.')

    @event.on('channel', 'foo')
    async def succeed():
        return 1

    @event.on('channel', 'foo')
    async def error():
        raise exc

    assert await event.emit('channel', 'foo') == [1, exc]

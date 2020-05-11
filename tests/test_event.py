from juno.components import Events


async def test_events() -> None:
    events = Events()
    exc = Exception('Expected error.')

    @events.on('channel', 'foo')
    async def succeed():
        return 1

    @events.on('channel', 'foo')
    async def error():
        raise exc

    assert await events.emit('channel', 'foo') == [1, exc]

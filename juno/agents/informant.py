class Informant:

    def __init__(services):
        self._exchange = services['exchange']
        self._symbol_info = {}

    async def __aenter__(self):
        self._symbol_info = await self._exchange.get_symbol_info()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

import aiohttp.client_exceptions

from juno.http import ClientResponse


class ExchangeException(Exception):
    """Error with connection or on the server side. Operation should be retried."""

    @staticmethod
    async def raise_for_status(response: ClientResponse) -> None:
        if response.status >= 400:
            try:
                content = await response.json()
            except aiohttp.client_exceptions.ContentTypeError:
                content = await response.text()
            raise ExchangeException(f"No handling for error {response.status} {content}")


class BadOrder(Exception):
    pass


class OrderWouldBeTaker(BadOrder):
    pass


class OrderMissing(BadOrder):
    pass


class InsufficientFunds(BadOrder):
    pass

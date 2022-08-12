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
    """Error with an order operation. May or may not be retried depending on the context."""

    pass


class OrderWouldBeTaker(BadOrder):
    """A limit order that would act as a market order. This is only raised in case of post-only
    limit orders."""

    pass


class OrderMissing(BadOrder):
    """Order missing during cancellation request (including when cancelling through edit order).
    Either the user provided an incorrect ID or the order was filled during the request."""

    pass


class InsufficientFunds(BadOrder):
    """The user no longer has sufficient balance. Either the user provided an incorrect value or
    there was a trade during the request which changed the original balance."""

    pass


class OrderWouldBeTaker(BadOrder):
    pass


class OrderMissing(BadOrder):
    pass


class InsufficientFunds(BadOrder):
    pass

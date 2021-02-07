class ExchangeException(Exception):
    pass


class OrderWouldBeTaker(Exception):
    pass


class OrderMissing(Exception):
    pass


class BadOrder(Exception):
    pass

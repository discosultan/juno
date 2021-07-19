from juno.components import Informant, Orderbook, User

from .limit import Limit


class LimitMatching(Limit):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
        cancel_order_on_error: bool = True,
    ) -> None:
        Limit.__init__(
            self,
            informant,
            orderbook,
            user,
            cancel_order_on_error,
            order_placement_strategy="matching",
        )

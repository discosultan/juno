from juno.components import Informant, Orderbook, User

from .limit import Limit


# TODO: Consolidate into limit broker.
class LimitLeadingEdit(Limit):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
        cancel_order_on_error: bool = True,
    ) -> None:
        Limit.__init__(
            self,
            informant=informant,
            orderbook=orderbook,
            user=user,
            cancel_order_on_error=cancel_order_on_error,
            use_edit_order_if_possible=True,
            order_placement_strategy="leading",
        )

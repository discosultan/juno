from typing import Callable

from juno.components import Informant, Orderbook, User
from juno.utils import short_uuid4

from .limit import Limit


class LimitLeading(Limit):
    def __init__(
        self,
        informant: Informant,
        orderbook: Orderbook,
        user: User,
        get_client_id: Callable[[], str] = short_uuid4,
        cancel_order_on_error: bool = True,
    ) -> None:
        Limit.__init__(
            self,
            informant,
            orderbook,
            user,
            get_client_id,
            cancel_order_on_error,
            order_placement_strategy='leading',
        )

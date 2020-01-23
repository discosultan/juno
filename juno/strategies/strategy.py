from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Dict, Tuple, Union

from juno import Advice, Candle, Trend
from juno.math import Constraint


class Meta:
    def __init__(
        self,
        constraints: Dict[Union[str, Tuple[str, ...]], Constraint] = {},
    ) -> None:
        self.constraints = constraints


class Strategy(ABC):
    meta: Meta

    @abstractproperty
    def advice(self) -> Advice:
        self._advice = 

    @abstractproperty
    def req_history(self) -> int:
        pass

    @abstractmethod
    def update(self, candle: Candle) -> Advice:
        pass

    def validate(self, *args: Any) -> None:
        # Assumes ordered.
        from_index = 0
        for names, constraint in type(self).meta.constraints.items():
            # Normalize scalars into a single element tuples.
            if not isinstance(names, tuple):
                names = names,

            to_index = from_index + len(names)
            inputs = args[from_index:to_index]

            if not constraint.validate(*inputs):
                raise ValueError(
                    f'Incorrect argument(s): {",".join(map(str, inputs))} for parameter(s): '
                    f'{",".join(names)}'
                )

            from_index = to_index

    # @staticmethod
    # def advice(trend: Trend, changed: bool) -> Advice:
    #     return {
    #         Trend.UP: Advice.BUY,
    #         Trend.DOWN: Advice.SELL,
    #     }.get(trend, Advice.NONE) if changed else Advice.NONE


class Persistence:
    """The number of ticks required to confirm a trend."""
    def __init__(self, level: int, allow_initial_trend: bool = False) -> None:
        self.age = 0
        self.level = level
        self.allow_next_trend = allow_initial_trend
        self.trend = Trend.UNKNOWN
        self.potential_trend = Trend.UNKNOWN

    def update(self, trend: Trend) -> Tuple[Trend, bool]:
        trend_changed = False

        if trend is Trend.UNKNOWN or (
            self.potential_trend is not Trend.UNKNOWN and trend is not self.potential_trend
        ):
            self.allow_next_trend = True

        if trend is not self.potential_trend:
            self.age = 0
            self.potential_trend = trend

        if (
            self.allow_next_trend and self.age == self.level
            and self.potential_trend is not self.trend
        ):
            self.trend = self.potential_trend
            trend_changed = True

        self.age += 1

        return self.trend, trend_changed

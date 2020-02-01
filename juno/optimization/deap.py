from random import Random
from typing import Any, Callable, Tuple


def mut_individual(random: Random) -> Callable[[list, Any, float], Tuple[list]]:
    def inner(individual: list, attrs: Any, indpb: float) -> Tuple[list]:
        for i, attr in enumerate(attrs):
            if random.random() < indpb:
                individual[i] = attr()
        return individual,
    return inner


def cx_individual(random: Random) -> Callable[[list, list], Tuple[list, list]]:
    def inner(ind1: list, ind2: list) -> Tuple[list, list]:
        stop = len(ind1)

        # Variant A.
        cxpoint1, cxpoint2 = 0, 0
        while cxpoint2 < cxpoint1:
            cxpoint1 = random.randrange(0, stop)
            cxpoint2 = random.randrange(0, stop)

        # Variant B.
        # cxpoint1 = random.randrange(0, stop)
        # cxpoint2 = random.randrange(cxpoint1, stop)

        cxpoint2 += 1

        ind1[cxpoint1:cxpoint2], ind2[cxpoint1:cxpoint2] = (
            ind2[cxpoint1:cxpoint2], ind1[cxpoint1:cxpoint2]
        )

        return ind1, ind2
    return inner


def cx_uniform(random: Random) -> Callable[[list, list, float], Tuple[list, list]]:
    def inner(ind1: list, ind2: list, indpb: float) -> Tuple[list, list]:
        size = min(len(ind1), len(ind2))
        for i in range(size):
            if random.random() < indpb:
                ind1[i], ind2[i] = ind2[i], ind1[i]

        return ind1, ind2
    return inner

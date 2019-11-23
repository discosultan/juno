import random

from typing import Any, Tuple


def mut_individual(individual: list, attrs: Any, indpb: float) -> Tuple[list]:
    for i, attr in enumerate(attrs):
        if random.random() < indpb:
            individual[i] = attr()
    return individual,


def cx_individual(ind1: list, ind2: list) -> Tuple[list, list]:
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

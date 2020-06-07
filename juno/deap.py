from random import Random
from typing import Any, Tuple

from deap import tools


def mut_individual(random: Random, individual: list, attrs: Any, indpb: float) -> Tuple[list]:
    for i, attr in enumerate(attrs):
        if random.random() < indpb:
            individual[i] = attr()
    return individual,


def cx_individual(random: Random, ind1: list, ind2: list) -> Tuple[list, list]:
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


def cx_uniform(random: Random, ind1: list, ind2: list, indpb: float) -> Tuple[list, list]:
    size = min(len(ind1), len(ind2))
    for i in range(size):
        if random.random() < indpb:
            ind1[i], ind2[i] = ind2[i], ind1[i]

    return ind1, ind2


# In addition to supporting passing in random, it also accepts a pair cancellation tokens.
def ea_mu_plus_lambda(
    random, population, toolbox, mu, lambda_, cxpb, mutpb, ngen, stats=None, halloffame=None,
    verbose=__debug__, cancellation_request=None, cancellation_response=None
):
    logbook = tools.Logbook()
    logbook.header = ['gen', 'nevals'] + (stats.fields if stats else [])

    # Evaluate the individuals with an invalid fitness
    invalid_ind = [ind for ind in population if not ind.fitness.valid]
    fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
    for ind, fit in zip(invalid_ind, fitnesses):
        ind.fitness.values = fit

    if halloffame is not None:
        halloffame.update(population)

    record = stats.compile(population) if stats is not None else {}
    logbook.record(gen=0, nevals=len(invalid_ind), **record)
    if verbose:
        print(logbook.stream)

    # Begin the generational process
    for gen in range(1, ngen + 1):
        # Vary the population
        offspring = _var_or(random, population, toolbox, lambda_, cxpb, mutpb)

        # Evaluate the individuals with an invalid fitness
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        # Update the hall of fame with the generated individuals
        if halloffame is not None:
            halloffame.update(offspring)

        # Select the next generation population
        population[:] = toolbox.select(population + offspring, mu)

        # Update the statistics with the new population
        record = stats.compile(population) if stats is not None else {}
        logbook.record(gen=gen, nevals=len(invalid_ind), **record)
        if verbose:
            print(logbook.stream)

        # Cancel if requested
        if cancellation_request and cancellation_request.is_set():
            if cancellation_response:
                cancellation_response.set()
            break

    return population, logbook


def _var_or(random, population, toolbox, lambda_, cxpb, mutpb):
    assert (cxpb + mutpb) <= 1.0, (
        'The sum of the crossover and mutation probabilities must be smaller or equal to 1.0.'
    )

    offspring = []
    for _ in range(lambda_):
        op_choice = random.random()
        if op_choice < cxpb:            # Apply crossover
            ind1, ind2 = map(toolbox.clone, random.sample(population, 2))
            ind1, ind2 = toolbox.mate(ind1, ind2)
            del ind1.fitness.values
            offspring.append(ind1)
        elif op_choice < cxpb + mutpb:  # Apply mutation
            ind = toolbox.clone(random.choice(population))
            ind, = toolbox.mutate(ind)
            del ind.fitness.values
            offspring.append(ind)
        else:                           # Apply reproduction
            offspring.append(random.choice(population))

    return offspring

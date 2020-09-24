use crate::{
    genetics::{
        Individual,
        crossover::Crossover,
        evaluation::Evaluation,
        mutation::Mutation,
        selection::Selection,
    },
};
use rand::prelude::*;
use std::time;

pub struct GeneticAlgorithm<TE, TS, TC, TM>
where
    TE: Evaluation,
    TS: Selection,
    TC: Crossover,
    TM: Mutation,
{
    evaluation: TE,
    selection: TS,
    crossover: TC,
    mutation: TM,
}

impl<TE, TS, TC, TM> GeneticAlgorithm<TE, TS, TC, TM>
where
    TE: Evaluation,
    TS: Selection,
    TC: Crossover,
    TM: Mutation,
{
    pub fn new(
        evaluation: TE,
        selection: TS,
        crossover: TC,
        mutation: TM,
    ) -> Self {
        Self {
            evaluation,
            selection,
            crossover,
            mutation,
        }
    }

    pub fn evolve(&self) {
        let population_size = 1000;
        let generations = 500;
        let seed = 1;

        assert!(population_size >= 2);
        // TODO: Get rid of this assertion.
        assert_eq!(population_size % 2, 0);

        let mut rng = StdRng::seed_from_u64(seed);

        let mut parents: Vec<Individual<TE::Chromosome>> = (0..population_size)
            .map(|_| Individual::generate(&mut rng))
            .collect();
        self.evaluate_and_sort_by_fitness_desc(&mut parents);

        let mut offsprings = Vec::with_capacity(population_size);

        for i in 0..generations {
            println!("gen {}", i);
            self.run_generation(&mut rng, &mut parents, &mut offsprings);
            std::mem::swap(&mut parents, &mut offsprings);
        }

        // Print best.
        println!("{} {:?}", offsprings[0].fitness, offsprings[0].chromosome);
    }

    fn run_generation(
        &self,
        rng: &mut StdRng,
        parents: &mut Vec<Individual<TE::Chromosome>>,
        offsprings: &mut Vec<Individual<TE::Chromosome>>,
    ) {
        // select
        let start = time::Instant::now();
        offsprings.clear();
        self.selection.select(parents, offsprings, parents.len());
        println!("select {:?}", start.elapsed());

        // crossover & mutation
        let start = time::Instant::now();
        for i in (0..offsprings.len()).step_by(2) {
            // TODO: Ugly.
            let (a, b) = offsprings.split_at_mut(i + 1);
            let chromosome1 = &mut a[a.len() - 1].chromosome;
            let chromosome2 = &mut b[0].chromosome;
            // TODO: Support using more than two parents.
            // let (mut child1, mut child2) = self.crossover.cross(
            //     rng,
            //     &offsprings[i].chromosome,
            //     &offsprings[i + 1].chromosome,
            // );
            self.crossover.cross(rng, chromosome1, chromosome2);
            // mutate
            self.mutation.mutate(rng, chromosome1);
            self.mutation.mutate(rng, chromosome2);
            // // reinsert
            // offspring.push(child1);
            // offspring.push(child2);
        }
        println!("cx & mutation {:?}", start.elapsed());

        // evaluate
        self.evaluate_and_sort_by_fitness_desc(offsprings);
    }

    fn evaluate_and_sort_by_fitness_desc(&self, population: &mut Vec<Individual<TE::Chromosome>>) {
        let start = time::Instant::now();
        self.evaluation.evaluate(population);
        println!("evaluation {:?}", start.elapsed());

        let start = time::Instant::now();
        population.sort_by(|ind1, ind2| ind2.fitness.partial_cmp(&ind1.fitness).unwrap());
        println!("sorting {:?}", start.elapsed());
    }
}

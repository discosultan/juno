use crate::genetics::{
    crossover::Crossover, mutation::Mutation, reinsertion::Reinsertion, selection::Selection,
    Evaluation, Individual,
};
use rand::prelude::*;
use std::time;

pub struct GeneticAlgorithm<TE, TS, TC, TM, TR>
where
    TE: Evaluation,
    TS: Selection,
    TC: Crossover,
    TM: Mutation,
    TR: Reinsertion,
{
    pub evaluation: TE,
    pub selection: TS,
    pub crossover: TC,
    pub mutation: TM,
    pub reinsertion: TR,
}

impl<TE, TS, TC, TM, TR> GeneticAlgorithm<TE, TS, TC, TM, TR>
where
    TE: Evaluation,
    TS: Selection,
    TC: Crossover,
    TM: Mutation,
    TR: Reinsertion,
{
    pub fn new(
        evaluation: TE,
        selection: TS,
        crossover: TC,
        mutation: TM,
        reinsertion: TR,
    ) -> Self {
        Self {
            evaluation,
            selection,
            crossover,
            mutation,
            reinsertion,
        }
    }

    pub fn evolve(
        &self,
        population_size: usize,
        generations: usize,
        seed: Option<u64>,
    ) -> Vec<Individual<TE::Chromosome>> {
        assert!(population_size >= 2);
        // TODO: Get rid of this assertion.
        assert_eq!(population_size % 2, 0);

        let seed = match seed {
            Some(seed) => seed,
            None => rand::thread_rng().gen_range(0, u64::MAX),
        };
        println!("using seed {}", seed);

        let mut rng = StdRng::seed_from_u64(seed);

        let mut gens = Vec::with_capacity(generations);

        let mut parents = (0..population_size)
            .map(|_| Individual::generate(&mut rng))
            .collect();
        self.evaluate_and_sort_by_fitness_desc(&mut parents);
        gens.push(parents[0].clone());
        println!("gen 0 best fitness {}", parents[0].fitness);

        let mut offsprings = Vec::with_capacity(population_size as usize);

        for i in 1..=generations {
            self.run_generation(&mut rng, &mut parents, &mut offsprings, population_size);

            std::mem::swap(&mut parents, &mut offsprings);
            offsprings.clear();

            gens.push(parents[0].clone());
            println!("gen {} best fitness {}", i, parents[0].fitness);
        }

        gens
    }

    fn run_generation(
        &self,
        rng: &mut StdRng,
        parents: &mut Vec<Individual<TE::Chromosome>>,
        offsprings: &mut Vec<Individual<TE::Chromosome>>,
        population_size: usize,
    ) {
        // select
        let start = time::Instant::now();
        self.selection
            .select(rng, parents, offsprings, self.reinsertion.selection_rate());
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
        // reinsert
        self.reinsertion
            .reinsert(parents, offsprings, population_size)
    }

    fn evaluate_and_sort_by_fitness_desc(&self, population: &mut Vec<Individual<TE::Chromosome>>) {
        let start = time::Instant::now();
        self.evaluation.evaluate(population);
        println!("evaluation {:?}", start.elapsed());

        let start = time::Instant::now();
        population.sort_by(Individual::fitness_desc);
        println!("sorting {:?}", start.elapsed());
    }
}

use crate::genetics::{
    crossover::Crossover, mutation::Mutation, reinsertion::Reinsertion, selection::Selection,
    Evaluation, Evolution, Generation, Individual, Timings,
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
        hall_of_fame_size: usize,
        seed: Option<u64>,
        on_generation: fn(usize, &Generation<TE::Chromosome>) -> (),
    ) -> Evolution<TE::Chromosome> {
        assert!(population_size >= 2);
        assert!(hall_of_fame_size >= 1);

        let seed = match seed {
            Some(seed) => seed,
            None => rand::thread_rng().gen_range(0..=u64::MAX),
        };

        let mut rng = StdRng::seed_from_u64(seed);

        let mut generations: Vec<Generation<TE::Chromosome>> = Vec::with_capacity(generations);

        let mut timings = Timings::default();

        let mut parents = (0..population_size)
            .map(|_| Individual::generate(&mut rng))
            .collect();
        self.evaluate_and_sort_by_fitness_desc(&mut parents, &mut timings);
        let generation = Generation {
            hall_of_fame: parents.iter().cloned().take(hall_of_fame_size).collect(),
            timings,
        };
        on_generation(0, &generation);
        generations.push(generation);

        let mut offsprings = Vec::with_capacity(population_size as usize);

        for gen in 1..=generations.capacity() {
            let mut timings = Timings::default();

            self.run_generation(
                &mut rng,
                &mut parents,
                &mut offsprings,
                population_size,
                &mut timings,
            );

            std::mem::swap(&mut parents, &mut offsprings);
            offsprings.clear();

            let generation = Generation {
                hall_of_fame: parents.iter().cloned().take(hall_of_fame_size).collect(),
                timings,
            };
            on_generation(gen, &generation);
            generations.push(generation);
        }

        Evolution { generations, seed }
    }

    fn run_generation(
        &self,
        rng: &mut StdRng,
        parents: &mut Vec<Individual<TE::Chromosome>>,
        offsprings: &mut Vec<Individual<TE::Chromosome>>,
        population_size: usize,
        timings: &mut Timings,
    ) {
        // select
        let start = time::Instant::now();
        self.selection
            .select(rng, parents, offsprings, self.reinsertion.selection_rate());
        timings.selection = start.elapsed();

        // crossover & mutation
        let start = time::Instant::now();
        for i in (0..offsprings.len()).step_by(2) {
            // TODO: Ugly.
            // If is last, we wrap around and take the first offspring to pair.
            let is_last = i == offsprings.len() - 1;
            let (chromosome1, chromosome2) = if is_last {
                let (a, b) = offsprings.split_at_mut(i);
                (&mut b[0].chromosome, &mut a[0].chromosome)
            } else {
                let (a, b) = offsprings.split_at_mut(i + 1);
                (&mut a[a.len() - 1].chromosome, &mut b[0].chromosome)
            };
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
        timings.crossover_mutation = start.elapsed();

        // evaluate
        self.evaluate_and_sort_by_fitness_desc(offsprings, timings);
        // reinsert
        self.reinsertion
            .reinsert(parents, offsprings, population_size)
    }

    fn evaluate_and_sort_by_fitness_desc(
        &self,
        population: &mut Vec<Individual<TE::Chromosome>>,
        timings: &mut Timings,
    ) {
        let start = time::Instant::now();
        self.evaluation.evaluate(population);
        timings.evaluation = start.elapsed();

        let start = time::Instant::now();
        population.sort_by(Individual::fitness_desc);
        timings.sorting = start.elapsed();
    }
}

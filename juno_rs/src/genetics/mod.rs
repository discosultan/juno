mod crossover;
mod evaluation;
mod mutation;
mod selection;

use crate::{
    genetics::{
        crossover::Crossover,
        evaluation::Evaluation,
        mutation::Mutation,
        selection::Selection,
    },
    strategies::Strategy,
};
use juno_derive_rs::*;
use rand::{rngs::StdRng, Rng, SeedableRng};
use std::iter;

pub trait Chromosome: Clone {
    fn len() -> usize;
    fn generate(rng: &mut StdRng) -> Self;
    fn mutate(&mut self, rng: &mut StdRng, i: usize);
    fn cross(&mut self, parent: &Self, i: usize);
}

// We need to manually implement clone because of:
// https://github.com/rust-lang/rust/issues/26925
// #[derive(Clone)]
pub struct Individual<T: Chromosome> {
    trader: TraderParams,
    strategy: T,
}

impl<T: Chromosome> Chromosome for Individual<T> {
    fn len() -> usize {
        TraderParams::len() + T::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            trader: TraderParams::generate(rng),
            strategy: T::generate(rng),
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        if i < TraderParams::len() {
            self.trader.mutate(rng, i);
        } else {
            self.strategy.mutate(rng, i - TraderParams::len());
        }
    }

    fn cross(&mut self, parent: &Individual<T>, i: usize) {
        if i < TraderParams::len() {
            self.trader.cross(&parent.trader, i);
        } else {
            self.strategy
                .cross(&parent.strategy, i - TraderParams::len());
        }
    }
}

impl<T: Chromosome> Clone for Individual<T> {
    fn clone(&self) -> Self {
        Self {
            trader: self.trader.clone(),
            strategy: self.strategy.clone(),
        }
    }
}

#[derive(Chromosome, Clone)]
struct TraderParams {
    pub missed_candle_policy: u32,
    pub stop_loss: f64,
    pub trail_stop_loss: bool,
    pub take_profit: f64,
}

fn missed_candle_policy(rng: &mut StdRng) -> u32 {
    rng.gen_range(0, 3)
}
fn stop_loss(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) {
        0.0
    } else {
        rng.gen_range(0.0001, 0.9999)
    }
}
fn trail_stop_loss(rng: &mut StdRng) -> bool {
    rng.gen_bool(0.5)
}
fn take_profit(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) {
        0.0
    } else {
        rng.gen_range(0.0001, 9.9999)
    }
}

pub struct GeneticAlgorithm<TS, TC, TM>
where
    TS: Selection,
    TC: Crossover,
    TM: Mutation,
{
    evaluation: Evaluation,
    selection: TS,
    crossover: TC,
    mutation: TM,
}

impl<TS, TC, TM> GeneticAlgorithm<TS, TC, TM>
where
    TS: Selection,
    TC: Crossover,
    TM: Mutation,
{
    pub fn evolve<T: Strategy>(&mut self) {
        let population_size = 100;
        let generations = 10;
        let seed = 1;

        if population_size % 2 == 1 {
            panic!("odd population size not supported");
        }

        let mut rng = StdRng::seed_from_u64(seed);

        let population: Vec<Individual<T::Params>> = iter::repeat(population_size)
            .map(|_| Individual::generate(&mut rng))
            .collect();

        for _ in 0..generations {
            // TODO: evolve
            self.run_generation::<T>(&population, &mut rng);
        }
    }

    fn run_generation<T: Strategy>(
        &self,
        population: &Vec<Individual<T::Params>>,
        rng: &mut StdRng,
    ) {
        // evaluate
        let fitnesses: Vec<f64> = self.evaluation.evaluate::<T>(population);
        // select
        let selection_count = 10;
        let selected: Vec<usize> = self.selection.select(&fitnesses, selection_count);
        let parents: Vec<&Individual<T::Params>> =
            selected.iter().map(|i| &population[*i]).collect();
        // crossover
        for i in (0..parents.len()).step_by(2) {
            // TODO: Support using more than two parents.
            // TODO: Also use 
            let (mut child1, mut child2) = self.crossover.cross(rng, parents[i], parents[i + 1]);
            self.mutation.mutate(rng, &mut child1);
            self.mutation.mutate(rng, &mut child2);
        }

        // mutate
        // clone??
    }
}

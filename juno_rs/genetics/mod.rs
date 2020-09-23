mod crossover;
mod evaluation;
mod selection;

use field_count::FieldCount;
use rand::{Rng, SeedableRng, rngs::StdRng};
use std::iter;
use crate::{
    genetics::{
        evaluation::Evaluation,
        selection::Selection,
    },
    strategies::Strategy,
};

pub trait Chromosome: Clone + FieldCount {
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

impl<T: Chromosome> Individual<T> {
    pub fn generate(rng: &mut StdRng) -> Self {
        Self {
            trader: TraderParams::generate(rng),
            strategy: T::generate(rng),
        }
    }

    pub fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        if i < TraderParams::field_count() {
            self.trader.mutate(rng, i);
        } else {
            self.strategy.mutate(rng, i - TraderParams::field_count());
        }
    }

    pub fn cross(&mut self, parent: &Individual<T>, i: usize) {
        if i < TraderParams::field_count() {
            self.trader.cross(&parent.trader, i);
        } else {
            self.strategy.cross(&parent.strategy, i - TraderParams::field_count());
        }
    }

    pub fn length() -> usize {
        TraderParams::field_count() + T::field_count()
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

#[derive(Clone, FieldCount)]
struct TraderParams {
    pub missed_candle_policy: u32,
    pub stop_loss: f64,
    pub trail_stop_loss: bool,
    pub take_profit: f64,
}

impl Chromosome for TraderParams {
    fn generate(rng: &mut StdRng) -> Self {
        Self {
            missed_candle_policy: candle_policy(rng),
            stop_loss: stop_loss(rng),
            trail_stop_loss: trail_stop_loss(rng),
            take_profit: take_profit(rng),
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        match i {
            0 => self.missed_candle_policy = candle_policy(rng),
            1 => self.stop_loss = stop_loss(rng),
            2 => self.trail_stop_loss = trail_stop_loss(rng),
            3 => self.take_profit = take_profit(rng),
            _ => panic!("invalid index")
        };
    }

    fn cross(&mut self, parent: &Self, i: usize) {
        match i {
            0 => self.missed_candle_policy = parent.missed_candle_policy,
            1 => self.stop_loss = parent.stop_loss,
            2 => self.trail_stop_loss = parent.trail_stop_loss,
            3 => self.take_profit = parent.take_profit,
            _ => panic!("invalid index")
        };
    }
}

fn candle_policy(rng: &mut StdRng) -> u32 { rng.gen_range(0, 3) }
fn stop_loss(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 0.9999) }
}
fn trail_stop_loss(rng: &mut StdRng) -> bool { rng.gen_bool(0.5) }
fn take_profit(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 9.9999) }
}

pub struct GeneticAlgorithm<TS: Selection> {
    evaluation: Evaluation,
    selection: TS,
}

impl<TS> GeneticAlgorithm<TS> where TS: Selection {
    pub fn evolve<T: Strategy>(&self) {
        let population_size = 100;
        let generations = 10;
        let seed = 1;
    
        let mut rng = StdRng::seed_from_u64(seed);

        let mut population: Vec<Individual<T::Params>> = iter::repeat(population_size)
            .map(|_| Individual::generate(&mut rng))
            .collect();
    
        for _ in 0..generations {
            // TODO: evolve
            self.run_generation::<T>(&population, &mut rng);
        }
    }
    
    fn run_generation<T: Strategy>(
        &self, population: &Vec<Individual<T::Params>>, rng: &mut StdRng
    ) {
        // evaluate
        let fitnesses: Vec<f64> = self.evaluation.evaluate::<T>(population);
        // select
        let selection_count = 10;
        let selected: Vec<usize> = self.selection.select(&fitnesses, selection_count);
        let parents: Vec<&Individual<T::Params>> = selected
            .iter()
            .map(|i| &population[*i])
            .collect();
        // crossover

        // mutate
        // clone??
    }
}

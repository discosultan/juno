pub mod algorithm;
pub mod crossover;
pub mod evaluation;
pub mod mutation;
pub mod selection;

pub use algorithm::GeneticAlgorithm;

use juno_derive_rs::*;
use rand::prelude::*;
use std::fmt::Debug;

pub trait Chromosome: Clone + Debug + Send + Sync {
    fn len() -> usize;
    fn generate(rng: &mut StdRng) -> Self;
    fn cross(&mut self, other: &mut Self, i: usize);
    fn mutate(&mut self, rng: &mut StdRng, i: usize);
}

// We cannot derive Clone but need to manually implement it because of:
// https://github.com/rust-lang/rust/issues/26925
#[derive(Debug)]
pub struct Individual<T: Chromosome> {
    chromosome: T,
    fitness: f64,
}

impl<T: Chromosome> Individual<T> {
    fn new(chromosome: T) -> Self {
        Self {
            chromosome,
            fitness: f64::MIN,
        }
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            chromosome: T::generate(rng),
            fitness: f64::MIN,
        }
    }
}

impl<T: Chromosome> Clone for Individual<T> {
    fn clone(&self) -> Self {
        Self {
            chromosome: self.chromosome.clone(),
            fitness: f64::MIN,
        }
    }
}

#[derive(Clone, Debug)]
pub struct TradingChromosome<T: Chromosome> {
    trader: TraderParams,
    strategy: T,
}

impl<T: Chromosome> Chromosome for TradingChromosome<T> {
    fn len() -> usize {
        TraderParams::len() + T::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            trader: TraderParams::generate(rng),
            strategy: T::generate(rng),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        if i < TraderParams::len() {
            self.trader.cross(&mut other.trader, i);
        } else {
            self.strategy
                .cross(&mut other.strategy, i - TraderParams::len());
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        if i < TraderParams::len() {
            self.trader.mutate(rng, i);
        } else {
            self.strategy.mutate(rng, i - TraderParams::len());
        }
    }
}

#[derive(Chromosome, Clone, Debug)]
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

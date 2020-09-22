mod crossover;
mod evaluation;
mod selection;

use rand::{Rng, SeedableRng, rngs::StdRng};
use std::iter;
use crate::{
    genetics::{
        evaluation::Evaluation,
        selection::Selection,
    },
    strategies::Strategy,
};
// We need to manually implement clone because of:
// https://github.com/rust-lang/rust/issues/26925
// #[derive(Clone)]
pub struct Individual<T: Strategy> {
    trader: TraderParams,
    strategy: T::Params,
}

impl<T: Strategy> Clone for Individual<T> {
    fn clone(&self) -> Self {
        Self {
            trader: self.trader.clone(),
            strategy: self.strategy.clone(),
        }
    }
}

#[derive(Clone)]
struct TraderParams {
    pub missed_candle_policy: u32,
    pub stop_loss: f64,
    pub trail_stop_loss: bool,
    pub take_profit: f64,
}

impl TraderParams {
    fn generate(rng: &mut StdRng) -> Self {
        Self {
            missed_candle_policy: rng.gen_range(0, 3),
            stop_loss: if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 0.9999) },
            trail_stop_loss: rng.gen_bool(0.5),
            take_profit: if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 9.9999) },
        }
    }
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

        let mut population: Vec<Individual<T>> = iter::repeat(population_size)
            .map(|_| Individual {
                trader: TraderParams::generate(&mut rng),
                strategy: T::generate(&mut rng)
            })
            .collect();
    
        for _ in 0..generations {
            // TODO: evolve
            self.run_generation(&mut population, &mut rng);
        }
    }
    
    fn run_generation<T: Strategy>(&self, population: &Vec<Individual<T>>, rng: &mut StdRng) {
        // evaluate
        let fitnesses: Vec<f64> = self.evaluation.evaluate(population);
        // select
        let selection_count = 10;
        let selected: Vec<usize> = self.selection.select(&fitnesses, selection_count);
        let parents: Vec<&Individual<T>> = selected.iter().map(|i| &population[*i]).collect();
        // crossover

        // mutate
        // clone??
    }
}

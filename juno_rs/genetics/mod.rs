use rand::{Rng, SeedableRng, rngs::StdRng};
use rayon::prelude::*;
use std::iter;

pub trait Chromosome {
    fn generate(rng: &mut StdRng) -> Self;
}

struct Individual<T: Chromosome> {
    trader: TraderParams,
    strategy: T,
}

struct TraderParams {
    pub missed_candle_policy: u32,
    pub stop_loss: f64,
    pub trail_stop_loss: bool,
    pub take_profit: f64,
}

impl Chromosome for TraderParams {
    fn generate(rng: &mut StdRng) -> Self {
        Self {
            missed_candle_policy: rng.gen_range(0, 3),
            stop_loss: if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 0.9999) },
            trail_stop_loss: rng.gen_bool(0.5),
            take_profit: if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 9.9999) },
        }
    }
}

pub fn evolve<T: Chromosome>() {
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
        run_generation(&mut population, &mut rng);
    }
}

fn run_generation<T: Chromosome>(population: &Vec<Individual<T>>, rng: &mut StdRng) {
    // TODO: Support different strategies here. A la parallel cpu or gpu, for example.
    // let fitnesses = Vec::with_capacity(population.len());
    // let fitness_slices = fitnesses.chunks_exact_mut(1).collect();

    // evaluate
    let fitnesses: Vec<f64> = 
    // select
    // crossover
    // mutate
    // clone??
}

struct Evaluator {
    
}

impl Evaluator {
    pub fn evaluate<T: Chromosome>(&self, population: &Vec<Individual<T>>) -> Vec<f64> {
        population
            .iter()
            .map(|ind| self.evaluate_individual(ind))
            .collect()
    }

    fn evaluate_individual<T: Chromosome>(&self, ind: &Individual<T>) -> f64 {
        1.0
    }
}

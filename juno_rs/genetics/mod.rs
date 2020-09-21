mod evaluation;

use rand::{Rng, SeedableRng, rngs::StdRng};
use std::iter;
use crate::strategies::Strategy;

pub struct Individual<T: Strategy> {
    trader: TraderParams,
    strategy: T::Params,
}

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

pub struct GeneticAlgorithm {
    evaliation: evaluation::Evaluation,
}

impl GeneticAlgorithm {
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
        // TODO: Support different strategies here. A la parallel cpu or gpu, for example.
        // let fitnesses = Vec::with_capacity(population.len());
        // let fitness_slices = fitnesses.chunks_exact_mut(1).collect();
    
        // evaluate
        let fitnesses: Vec<f64> = self.evaliation.evaluate(population);
        // select
        // crossover
        // mutate
        // clone??
    }
}

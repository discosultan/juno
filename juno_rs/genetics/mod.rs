use rand::{Rng, SeedableRng, rngs::StdRng};
// use rayon::prelude::*;
use std::iter;
use crate::{common, storages, strategies::Strategy, traders};

struct Individual<T: Strategy> {
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

pub fn evolve<T: Strategy>() {
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

fn run_generation<T: Strategy>(population: &Vec<Individual<T>>, rng: &mut StdRng) {
    // TODO: Support different strategies here. A la parallel cpu or gpu, for example.
    // let fitnesses = Vec::with_capacity(population.len());
    // let fitness_slices = fitnesses.chunks_exact_mut(1).collect();

    // evaluate
    // let fitnesses: Vec<f64> = 
    // select
    // crossover
    // mutate
    // clone??
}

struct Evaluator {
    exchange_info: common::ExchangeInfo,
    candles: Vec<common::Candle>,
    symbol: String,
    base_asset: String,
    quote_asset: String,
    interval: u64,
    quote: f64,
}

impl Evaluator {
    pub fn new(
        exchange: &str, symbol: &str, interval: u64, start: u64, end: u64, quote: f64
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let dash_i = symbol.find('-').ok_or("invalid symbol")?;
        Ok(Self {
            exchange_info: storages::get_exchange_info(exchange)?,
            candles: storages::list_candles(exchange, symbol, interval, start, end)?,
            symbol: symbol.into(),
            base_asset: symbol[dash_i..].into(),
            quote_asset: symbol[0..dash_i].into(),
            interval,
            quote,
        })
    }

    pub fn evaluate<T: Strategy>(&self, population: &Vec<Individual<T>>) -> Vec<f64> {
        population
            .iter()
            .map(|ind| self.evaluate_individual(ind))
            .collect()
    }

    fn evaluate_individual<T: Strategy>(&self, ind: &Individual<T>) -> f64 {
        let _summary = traders::trade::<T>(
            &ind.strategy,
            &self.candles,
            &self.exchange_info.fees[&self.symbol],
            &self.exchange_info.filters[&self.symbol],
            &self.exchange_info.borrow_info[&self.symbol][&self.base_asset],
            2,
            self.interval,
            self.quote,
            ind.trader.missed_candle_policy,
            ind.trader.stop_loss,
            ind.trader.trail_stop_loss,
            ind.trader.take_profit,
            true,
            true,
        );
        1.0
    }
}

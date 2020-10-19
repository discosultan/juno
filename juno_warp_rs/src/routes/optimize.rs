use juno_rs::{
    fill_missing_candles,
    genetics::{crossover, mutation, reinsertion, selection, GeneticAlgorithm, Individual},
    prelude::*,
    statistics, storages,
    strategies::*,
    trading::{self, TradingChromosome, TradingSummary},
};
use serde::Deserialize;
use warp::{Filter, Rejection};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[derive(Debug, Deserialize)]
struct UserParams {
    exchange: String,
    interval: String,
    start: String,
    end: String,
    quote: f64,
    training_symbols: Vec<String>,
    validation_symbols: Vec<String>,
}

struct Params {
    exchange: String,
    interval: u64,
    start: u64,
    end: u64,
    quote: f64,
    training_symbols: Vec<String>,
    validation_symbols: Vec<String>,
}

impl From<UserParams> for Params {
    fn from(input: UserParams) -> Self {
        Self {
            exchange: input.exchange,
            interval: input.interval.to_interval(),
            start: input.start.to_timestamp(),
            end: input.end.to_timestamp(),
            quote: input.quote,
            training_symbols: input.training_symbols,
            validation_symbols: input.validation_symbols,
        }
    }
}

pub fn route() -> impl Filter<
    Extract = (warp::reply::Json,),
    Error = Rejection
> + Clone {
    warp::path!("optimize")
        .and(warp::body::json())
        .map(|args: UserParams| {
            let gens = optimize::<FourWeekRule>(&args.into()).unwrap();
            warp::reply::json(&gens)
        })
}

fn optimize<T: Signal>(args: &Params) -> Result<Vec<Individual<TradingChromosome<T::Params>>>> {
    let algo = GeneticAlgorithm::new(
        trading::BasicEvaluation::<T>::new(
            &args.exchange,
            &args.training_symbols,
            args.interval,
            args.start,
            args.end,
            args.quote,
        )?,
        selection::EliteSelection::default(),
        // selection::TournamentSelection::default(),
        // crossover::UniformCrossover::default(),
        crossover::UniformCrossover::new(0.75),
        // mutation::UniformMutation::default(),
        mutation::UniformMutation::new(0.25),
        // reinsertion::EliteReinsertion::default(),
        reinsertion::EliteReinsertion::new(0.75),
    );
    let population_size = 128;
    let generations = 128;
    let seed = Some(1);
    let gens = algo.evolve(population_size, generations, seed);
    Ok(gens)
}

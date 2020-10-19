use juno_rs::{
    fill_missing_candles,
    genetics::{crossover, mutation, reinsertion, selection, Chromosome, GeneticAlgorithm, Individual},
    prelude::*,
    statistics::TradingStats,
    storages,
    strategies::*,
    trading::{self, TradingChromosome, TradingSummary},
};
use serde::Deserialize;
use warp::{Filter, Rejection};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[derive(Debug, Deserialize)]
struct UserParams {
    population_size: usize,
    generations: usize,

    exchange: String,
    interval: String,
    start: String,
    end: String,
    quote: f64,
    training_symbols: Vec<String>,

    validation_symbols: Vec<String>,
}

struct Params {
    population_size: usize,
    generations: usize,

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
            population_size: input.population_size,
            generations: input.generations,

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

struct OptimizeResult<T: Chromosome> {
    ind: Individual<TradingChromosome<T>>,
    stats: TradingStats,
}

pub fn route() -> impl Filter<
    Extract = (warp::reply::Json,),
    Error = Rejection
> + Clone {
    warp::post()
        .and(warp::path("optimize"))
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
    let seed = Some(1);
    let gens = algo.evolve(args.population_size, args.generations, seed);
    Ok(gens)
}

fn backtest<T: Signal>(
    args: &Params,
    symbol: &str,
    chrom: &TradingChromosome<T::Params>,
) -> Result<TradingStats> {
    let candles =
        storages::list_candles(&args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    let summary = trading::trade::<T>(
        &chrom.strategy,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        args.interval,
        args.quote,
        chrom.trader.missed_candle_policy,
        chrom.trader.stop_loss,
        chrom.trader.trail_stop_loss,
        chrom.trader.take_profit,
        true,
        true,
    );

    let stats_interval = DAY_MS;
    let stats_candles =
        storages::list_candles(&args.exchange, symbol, stats_interval, args.start, args.end)?;
    let candles_missing_filled =
        fill_missing_candles(stats_interval, args.start, args.end, &stats_candles);
    let base_prices: Vec<f64> = candles_missing_filled
        .iter()
        .map(|candle| candle.close)
        .collect();

    // let stats = statistics::analyse(&base_prices, None, &[], &result, args.interval);
    // let sharpe = stats.sharpe_ratio;

    let stats = TradingStats::from_summary(&summary, &base_prices, stats_interval);

    Ok(stats)
}

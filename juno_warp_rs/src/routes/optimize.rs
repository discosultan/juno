use super::custom_reject;
use anyhow::Result;
use juno_rs::{
    chandler::fill_missing_candles,
    genetics::{
        crossover, mutation, reinsertion, selection, Chromosome, GeneticAlgorithm, Individual,
    },
    prelude::*,
    statistics::TradingStats,
    storages,
    strategies::*,
    trading::{self, TradingChromosome, TradingSummary},
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use warp::{reply::Json, Filter, Rejection};

#[derive(Debug, Deserialize)]
struct Params {
    population_size: usize,
    generations: usize,

    strategy: String, // TODO: Move to path param.
    exchange: String,
    #[serde(deserialize_with = "deserialize_interval")]
    interval: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    quote: f64,
    training_symbols: Vec<String>,

    validation_symbols: Vec<String>,
}

impl Params {
    fn iter_symbols(&self) -> impl Iterator<Item = &String> {
        self.training_symbols.iter().chain(&self.validation_symbols)
    }
}

#[derive(Serialize)]
struct Generation<T: Chromosome> {
    nr: usize,
    ind: Individual<TradingChromosome<T>>,
    symbol_summaries: HashMap<String, TradingSummary>,
    symbol_stats: HashMap<String, TradingStats>,
}

pub fn route() -> impl Filter<Extract = (warp::reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::path("optimize"))
        .and(warp::body::json())
        .and_then(|args: Params| async move {
            match args.strategy.as_ref() {
                "fourweekrule" => process::<FourWeekRule>(args),
                "triplema" => process::<TripleMA>(args),
                "doublema" => process::<DoubleMA>(args),
                "singlema" => process::<SingleMA>(args),
                "sig_fourweekrule" => process::<Sig<FourWeekRule>>(args),
                "sig_triplema" => process::<Sig<TripleMA>>(args),
                "sigosc_triplema_rsi" => process::<SigOsc<TripleMA, Rsi>>(args),
                "sigosc_doublema_rsi" => process::<SigOsc<DoubleMA, Rsi>>(args),
                strategy => panic!("unsupported strategy {}", strategy), // TODO: return 400
            }
            .map_err(|error| custom_reject(error))
        })
}

fn process<T: Signal>(args: Params) -> Result<Json> {
    let gens = optimize::<T>(&args)?;
    let mut last_fitness = f64::NAN;
    let gen_stats = gens
        .into_iter()
        .enumerate()
        .filter(|(_, ind)| {
            let pass = last_fitness.is_nan() || ind.fitness > last_fitness;
            last_fitness = ind.fitness;
            pass
        })
        .map(|(i, ind)| {
            let symbol_summaries = args
                .iter_symbols()
                .map(|symbol| {
                    let summary = backtest::<T>(&args, symbol, &ind.chromosome).unwrap();
                    (symbol.to_owned(), summary) // TODO: Return &String instead.
                })
                .collect::<HashMap<String, TradingSummary>>();
            let symbol_stats = symbol_summaries
                .iter()
                .map(|(symbol, summary)| {
                    let stats = get_stats(&args, symbol, summary).unwrap();
                    (symbol.to_owned(), stats) // TODO: Return &String instead.
                })
                .collect::<HashMap<String, TradingStats>>();
            Generation {
                nr: i,
                ind,
                symbol_summaries,
                symbol_stats,
            }
        })
        .collect::<Vec<Generation<T::Params>>>();
    Ok(warp::reply::json(&gen_stats))
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
) -> Result<TradingSummary> {
    let candles =
        storages::list_candles(&args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trading::trade::<T>(
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
    ))
}

fn get_stats(args: &Params, symbol: &str, summary: &TradingSummary) -> Result<TradingStats> {
    let stats_interval = DAY_MS;
    let stats_candles =
        storages::list_candles(&args.exchange, symbol, stats_interval, args.start, args.end)?;
    let candles_missing_filled =
        fill_missing_candles(stats_interval, args.start, args.end, &stats_candles)?;
    let base_prices: Vec<f64> = candles_missing_filled
        .iter()
        .map(|candle| candle.close)
        .collect();

    let stats = TradingStats::from_summary(&summary, &base_prices, stats_interval);

    Ok(stats)
}

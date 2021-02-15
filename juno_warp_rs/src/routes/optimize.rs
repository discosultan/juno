use super::custom_reject;
use anyhow::Result;
use juno_rs::{
    chandler::{candles_to_prices, fill_missing_candles},
    genetics::{
        crossover, mutation, reinsertion, selection, Chromosome, Evolution, GeneticAlgorithm,
        Individual,
    },
    statistics::Statistics,
    storages,
    time::{deserialize_timestamp, DAY_MS},
    trading::{
        trade, BasicEvaluation, EvaluationAggregation, EvaluationStatistic, TradingParams,
        TradingParamsContext, TradingSummary,
    },
    SymbolExt,
};
use serde::{Deserialize, Serialize};
use std::{cmp::min, collections::HashMap};
use warp::{reply, Filter, Rejection, Reply};

#[derive(Deserialize)]
struct Params {
    population_size: usize,
    generations: usize,
    hall_of_fame_size: usize,
    seed: Option<u64>,

    exchange: String,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    quote: f64,
    training_symbols: Vec<String>,

    validation_symbols: Vec<String>,

    evaluation_statistic: EvaluationStatistic,
    evaluation_aggregation: EvaluationAggregation,

    context: TradingParamsContext,
}

impl Params {
    fn iter_symbols(&self) -> impl Iterator<Item = &String> {
        self.training_symbols.iter().chain(&self.validation_symbols)
    }
}

#[derive(Serialize)]
struct Generation {
    // We need to store generation number because we are filtering out generations with not change
    // in top.
    nr: usize,
    hall_of_fame: Vec<IndividualStats>,
}

#[derive(Serialize)]
struct IndividualStats {
    ind: Individual<TradingParams>,
    symbol_stats: HashMap<String, Statistics>,
}

#[derive(Serialize)]
struct EvolutionStats {
    generations: Vec<Generation>,
    seed: u64,
}

#[derive(Serialize)]
struct Info {
    evaluation_statistics: [EvaluationStatistic; 4],
    evaluation_aggregations: [EvaluationAggregation; 3],
}

pub fn routes() -> impl Filter<Extract = impl Reply, Error = Rejection> + Clone {
    warp::path("optimize").and(get().or(post()))
}

fn get() -> impl Filter<Extract = (reply::Json,), Error = Rejection> + Clone {
    warp::get().map(|| {
        reply::json(&Info {
            evaluation_statistics: EvaluationStatistic::values(),
            evaluation_aggregations: EvaluationAggregation::values(),
        })
    })
}

fn post() -> impl Filter<Extract = (reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::body::json())
        .and_then(|args: Params| async move {
            process(args).map_err(|error| custom_reject(error)) // TODO: return 400
        })
}

fn process(args: Params) -> Result<reply::Json> {
    let evolution = optimize(&args)?;
    let mut best_fitnesses = vec![f64::NAN; args.hall_of_fame_size];
    let gen_stats = evolution
        .generations
        .into_iter()
        .enumerate()
        .filter(|(_, gen)| {
            let mut pass = false;
            for i in 0..min(args.hall_of_fame_size, gen.hall_of_fame.len()) {
                let best_ind = &gen.hall_of_fame[i];
                let best_fitness = best_fitnesses[i];
                if best_fitness.is_nan() || best_ind.fitness > best_fitness {
                    best_fitnesses[i] = best_ind.fitness;
                    pass = true;
                }
            }
            pass
        })
        .map(|(i, gen)| {
            let hall_of_fame = gen
                .hall_of_fame
                .into_iter()
                .map(|ind| {
                    let symbol_stats = args
                        .iter_symbols()
                        .map(|symbol| {
                            let summary = backtest(&args, symbol, &ind.chromosome).unwrap();
                            let stats = get_stats(&args, symbol, &summary).unwrap();
                            (symbol.to_owned(), stats) // TODO: Return &String instead.
                        })
                        .collect::<HashMap<String, Statistics>>();

                    IndividualStats { ind, symbol_stats }
                })
                .collect();

            Generation {
                nr: i,
                hall_of_fame,
            }
        })
        .collect::<Vec<Generation>>();
    Ok(reply::json(&EvolutionStats {
        generations: gen_stats,
        seed: evolution.seed,
    }))
}

fn optimize(args: &Params) -> Result<Evolution<TradingParams>> {
    let algo = GeneticAlgorithm::new(
        BasicEvaluation::new(
            &args.exchange,
            &args.training_symbols,
            &args.context.trader.intervals,
            args.start,
            args.end,
            args.quote,
            args.evaluation_statistic,
            args.evaluation_aggregation,
        )?,
        selection::EliteSelection { shuffle: false },
        // selection::GenerateRandomSelection {}, // For random search.
        crossover::UniformCrossover::new(0.5),
        mutation::UniformMutation::new(0.25),
        reinsertion::EliteReinsertion::new(0.75, 0.5),
        // reinsertion::PureReinsertion {}, // For random search.
    );
    let evolution = algo.evolve(
        args.population_size,
        args.generations,
        args.hall_of_fame_size,
        args.seed,
        on_generation,
        &args.context,
    );
    Ok(evolution)
}

fn on_generation<T: Chromosome>(nr: usize, gen: &juno_rs::genetics::Generation<T>) {
    println!("gen {} best fitness {}", nr, gen.hall_of_fame[0].fitness);
    println!("{:?}", gen.timings);
}

fn backtest(args: &Params, symbol: &str, chromosome: &TradingParams) -> Result<TradingSummary> {
    let candles = storages::list_candles(
        &args.exchange,
        symbol,
        chromosome.trader.interval,
        args.start,
        args.end,
    )?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trade(
        &chromosome.strategy,
        &chromosome.stop_loss,
        &chromosome.take_profit,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        chromosome.trader.interval,
        args.quote,
        chromosome.trader.missed_candle_policy,
        true,
        true,
    ))
}

fn get_stats(args: &Params, symbol: &str, summary: &TradingSummary) -> Result<Statistics> {
    let stats_interval = DAY_MS;

    // Stats base.
    let stats_candles =
        storages::list_candles(&args.exchange, symbol, stats_interval, args.start, args.end)?;
    let stats_candles = fill_missing_candles(stats_interval, args.start, args.end, &stats_candles)?;

    // Stats quote (optional).
    let stats_fiat_candles =
        storages::list_candles("coinbase", "btc-eur", stats_interval, args.start, args.end)?;
    let stats_fiat_candles =
        fill_missing_candles(stats_interval, args.start, args.end, &stats_fiat_candles)?;

    // let stats_quote_prices = None;
    let stats_quote_prices = Some(candles_to_prices(&stats_fiat_candles, None));
    let stats_base_prices = candles_to_prices(&stats_candles, stats_quote_prices.as_deref());

    let stats = Statistics::compose(
        &summary,
        &stats_base_prices,
        stats_quote_prices.as_deref(),
        stats_interval,
    );

    Ok(stats)
}

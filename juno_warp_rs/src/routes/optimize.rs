use super::custom_reject;
use anyhow::Result;
use juno_rs::{
    chandler::{candles_to_prices, fill_missing_candles},
    genetics::{
        crossover, mutation, reinsertion, selection, Chromosome, Evolution, GeneticAlgorithm,
        Individual,
    },
    prelude::*,
    statistics::TradingStats,
    storages,
    strategies::*,
    trading::{self, StopLoss, TakeProfit, TradingChromosome, TradingSummary},
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use warp::{reply::Json, Filter, Rejection};

#[derive(Debug, Deserialize)]
struct Params {
    population_size: usize,
    generations: usize,
    hall_of_fame_size: usize,
    seed: Option<u64>,

    strategy: String, // TODO: Move to path param.
    stop_loss: String,
    take_profit: String,
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
struct Generation<T: Chromosome, U: Chromosome, V: Chromosome> {
    // We need to store generation number because we are filtering out generations with not change
    // in top.
    nr: usize,
    hall_of_fame: Vec<IndividualStats<T, U, V>>,
}

#[derive(Serialize)]
struct IndividualStats<T: Chromosome, U: Chromosome, V: Chromosome> {
    ind: Individual<TradingChromosome<T, U, V>>,
    symbol_stats: HashMap<String, TradingStats>,
}

#[derive(Serialize)]
struct EvolutionStats<T: Chromosome, U: Chromosome, V: Chromosome> {
    generations: Vec<Generation<T, U, V>>,
    seed: u64,
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
                "sigosc_triplema_rsi" => {
                    process::<SigOsc<TripleMA, Rsi, EnforceOscillatorFilter>>(args)
                }
                "sigosc_doublema_rsi" => {
                    process::<SigOsc<DoubleMA, Rsi, EnforceOscillatorFilter>>(args)
                }
                "sigosc_fourweekrule_rsi_prevent" => {
                    process::<SigOsc<FourWeekRule, Rsi, PreventOscillatorFilter>>(args)
                }
                strategy => panic!("unsupported strategy {}", strategy), // TODO: return 400
            }
            .map_err(|error| custom_reject(error))
        })
}

fn process(args: Params) -> Result<Json> {
    let evolution = optimize::<T, U, V>(&args)?;
    let mut last_fitness = f64::NAN;
    let gen_stats = evolution
        .generations
        .into_iter()
        .enumerate()
        .filter(|(_, gen)| {
            let best_ind = &gen.hall_of_fame[0];
            let pass = last_fitness.is_nan() || best_ind.fitness > last_fitness;
            last_fitness = best_ind.fitness;
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
                            let summary =
                                backtest::<T, U, V>(&args, symbol, &ind.chromosome).unwrap();
                            let stats = get_stats(&args, symbol, &summary).unwrap();
                            (symbol.to_owned(), stats) // TODO: Return &String instead.
                        })
                        .collect::<HashMap<String, TradingStats>>();

                    IndividualStats { ind, symbol_stats }
                })
                .collect();

            Generation {
                nr: i,
                hall_of_fame,
            }
        })
        .collect::<Vec<Generation<T::Params, U::Params, V::Params>>>();
    Ok(warp::reply::json(&EvolutionStats {
        generations: gen_stats,
        seed: evolution.seed,
    }))
}

fn optimize<T: Signal, U: StopLoss, V: TakeProfit>(
    args: &Params,
) -> Result<Evolution<TradingChromosome<T::Params, U::Params, V::Params>>> {
    let algo = GeneticAlgorithm::new(
        trading::BasicEvaluation::<T, U, V>::new(
            &args.exchange,
            &args.training_symbols,
            args.interval,
            args.start,
            args.end,
            args.quote,
        )?,
        selection::EliteSelection { shuffle: false },
        // selection::TournamentSelection::default(),
        // crossover::UniformCrossover::default(),
        crossover::UniformCrossover::new(0.75),
        // mutation::UniformMutation::default(),
        mutation::UniformMutation::new(0.33),
        // reinsertion::EliteReinsertion::default(),
        reinsertion::EliteReinsertion::new(0.75),
    );
    let evolution = algo.evolve(
        args.population_size,
        args.generations,
        args.hall_of_fame_size,
        args.seed,
        on_generation,
    );
    Ok(evolution)
}

fn on_generation<T: Chromosome>(nr: usize, gen: &juno_rs::genetics::Generation<T>) {
    println!("gen {} best fitness {}", nr, gen.hall_of_fame[0].fitness);
    println!("{:?}", gen.timings);
}

fn backtest<T: Signal, U: StopLoss, V: TakeProfit>(
    args: &Params,
    symbol: &str,
    chrom: &TradingChromosome<T::Params, U::Params, V::Params>,
) -> Result<TradingSummary> {
    let candles =
        storages::list_candles(&args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trading::trade::<T, U, V>(
        &chrom.strategy,
        &chrom.stop_loss,
        &chrom.take_profit,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        args.interval,
        args.quote,
        chrom.trader.missed_candle_policy,
        true,
        true,
    ))
}

fn get_stats(args: &Params, symbol: &str, summary: &TradingSummary) -> Result<TradingStats> {
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

    let stats = TradingStats::from_summary(
        &summary,
        &stats_base_prices,
        stats_quote_prices.as_deref(),
        stats_interval,
    );

    Ok(stats)
}

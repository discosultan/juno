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
use warp::{Filter, Rejection};

#[derive(Debug, Deserialize)]
struct Params {
    strategy: String,
    exchange: String,
    #[serde(deserialize_with = "deserialize_interval")]
    interval: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    quote: f64,
    symbols: Vec<String>,
    strategy_params: String,
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
        .and(warp::path("backtest"))
        .and(warp::body::json())
        .map(|args: Params| {
            match args.strategy.as_ref() {
                "fourweekrule" => process::<FourWeekRule>(args),
                "triplema" => process::<TripleMA>(args),
                "doublema" => process::<DoubleMA>(args),
                "singlema" => process::<SingleMA>(args),
                "sig<fourweekrule>" => process::<Sig<FourWeekRule>>(args),
                "sig<triplema>" => process::<Sig<TripleMA>>(args),
                "sigosc<triplema,rsi>" => process::<SigOsc<TripleMA, Rsi>>(args),
                "sigosc<doublema,rsi>" => process::<SigOsc<DoubleMA, Rsi>>(args),
                strategy => panic!("unsupported strategy {}", strategy), // TODO: return 400
            }
        })
}

fn process<T: Signal>(args: Params) -> warp::reply::Json {
    let strategyParams: T::Params = serde_json::from_str(&args.strategyParams).unwrap();
    // let symbol_summaries = args.symbols
    //     .iter()
    //     .map(|symbol| {
    //         let summary = backtest::<T>(&args, symbol, &strategyParams).unwrap();
    //         (symbol.to_owned(), summary) // TODO: Return &String instead.
    //     })
    //     .collect::<HashMap<String, TradingSummary>>();
    // let symbol_stats = symbol_summaries
    //     .iter()
    //     .map(|(symbol, summary)| {
    //         let stats = get_stats(&args, symbol, summary).unwrap();
    //         (symbol.to_owned(), stats) // TODO: Return &String instead.
    //     })
    //     .collect::<HashMap<String, TradingStats>>();

    warp::reply::json(&1)
}

fn backtest<T: Signal>(
    strategy_arams: &T::Params,
    args: &Params,
    symbol: &str,
    chrom: &TradingChromosome<T::Params>,
) -> Result<TradingSummary> {
    let candles =
        storages::list_candles(&args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trading::trade::<T>(
        &strategy_arams,
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

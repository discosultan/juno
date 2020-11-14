use super::custom_reject;
use anyhow::Result;
use bytes::buf::Buf;
use juno_rs::{
    chandler::fill_missing_candles,
    prelude::*,
    statistics::TradingStats,
    storages,
    strategies::*,
    trading::{self, TraderParams, TradingSummary},
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use warp::{hyper::body::Bytes, reply::Json, Filter, Rejection};

#[derive(Debug, Deserialize)]
struct Params<T: Signal> {
    exchange: String,
    symbols: Vec<String>,
    #[serde(deserialize_with = "deserialize_interval")]
    interval: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    quote: f64,
    strategy_params: T::Params,
    trader_params: TraderParams,
}

#[derive(Serialize)]
struct TradingResult {
    symbol_summaries: HashMap<String, TradingSummary>,
    symbol_stats: HashMap<String, TradingStats>,
}

pub fn route() -> impl Filter<Extract = (warp::reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::path("backtest"))
        .and(warp::path::param())
        .and(warp::body::bytes())
        .and_then(|strategy: String, bytes: Bytes| async move {
            match strategy.as_ref() {
                "fourweekrule" => process::<FourWeekRule>(bytes),
                "triplema" => process::<TripleMA>(bytes),
                "doublema" => process::<DoubleMA>(bytes),
                "singlema" => process::<SingleMA>(bytes),
                "sig_fourweekrule" => process::<Sig<FourWeekRule>>(bytes),
                "sig_triplema" => process::<Sig<TripleMA>>(bytes),
                "sigosc_triplema_rsi" => process::<SigOsc<TripleMA, Rsi>>(bytes),
                "sigosc_doublema_rsi" => process::<SigOsc<DoubleMA, Rsi>>(bytes),
                strategy => panic!("unsupported strategy {}", strategy), // TODO: return 400
            }
            .map_err(|error| custom_reject(error))
        })
}

fn process<T: Signal>(bytes: Bytes) -> Result<Json> {
    let args: Params<T> = serde_json::from_reader(bytes.reader())?;

    let symbol_summaries = args
        .symbols
        .iter()
        .map(|symbol| {
            let summary = backtest::<T>(&args, symbol).expect("backtest");
            (symbol.to_owned(), summary) // TODO: Return &String instead.
        })
        .collect::<HashMap<String, TradingSummary>>();
    let symbol_stats = symbol_summaries
        .iter()
        .map(|(symbol, summary)| {
            let stats = get_stats(&args, symbol, summary).expect("get stats");
            (symbol.to_owned(), stats) // TODO: Return &String instead.
        })
        .collect::<HashMap<String, TradingStats>>();

    Ok(warp::reply::json(&TradingResult {
        symbol_summaries,
        symbol_stats,
    }))
}

fn backtest<T: Signal>(args: &Params<T>, symbol: &str) -> Result<TradingSummary> {
    let candles =
        storages::list_candles(&args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trading::trade::<T>(
        &args.strategy_params,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        args.interval,
        args.quote,
        args.trader_params.missed_candle_policy,
        args.trader_params.stop_loss,
        args.trader_params.trail_stop_loss,
        args.trader_params.take_profit,
        true,
        true,
    ))
}

fn get_stats<T: Signal>(
    args: &Params<T>,
    symbol: &str,
    summary: &TradingSummary,
) -> Result<TradingStats> {
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

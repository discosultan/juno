use super::custom_reject;
use anyhow::Result;
use bytes::buf::Buf;
use juno_derive_rs::*;
use juno_rs::{
    chandler::{candles_to_prices, fill_missing_candles},
    genetics::Chromosome,
    prelude::*,
    statistics::TradingStats,
    stop_loss::StopLoss,
    storages,
    strategies::*,
    take_profit::TakeProfit,
    trading::*,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use warp::{hyper::body::Bytes, reply::Json, Filter, Rejection};

#[derive(Debug, Deserialize)]
struct Params<T: Chromosome, U: Chromosome, V: Chromosome> {
    exchange: String,
    symbols: Vec<String>,
    #[serde(deserialize_with = "deserialize_interval")]
    interval: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    quote: f64,
    strategy_params: T,
    stop_loss_params: U,
    take_profit_params: V,
    #[serde(deserialize_with = "deserialize_missed_candle_policy")]
    missed_candle_policy: u32,
}

#[derive(Serialize)]
struct TradingResult {
    symbol_stats: HashMap<String, TradingStats>,
}

pub fn route() -> impl Filter<Extract = (warp::reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::path("backtest"))
        .and(warp::path::param()) // strategy
        .and(warp::path::param()) // stop_loss
        .and(warp::path::param()) // take_profit
        .and(warp::body::bytes())
        .and_then(
            |strategy: String, stop_loss: String, take_profit: String, bytes: Bytes| async move {
                route_strategy!(process, strategy, stop_loss, take_profit, bytes)
                    .map_err(|error| custom_reject(error))
            },
        )
}

fn process<T: Signal, U: StopLoss, V: TakeProfit>(bytes: Bytes) -> Result<Json> {
    let args: Params<T::Params, U::Params, V::Params> = serde_json::from_reader(bytes.reader())?;

    let symbol_summaries = args
        .symbols
        .iter()
        .map(|symbol| {
            let summary = backtest::<T, U, V>(&args, symbol).expect("backtest");
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

    Ok(warp::reply::json(&TradingResult { symbol_stats }))
}

fn backtest<T: Signal, U: StopLoss, V: TakeProfit>(
    args: &Params<T::Params, U::Params, V::Params>,
    symbol: &str,
) -> Result<TradingSummary> {
    let candles =
        storages::list_candles(&args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trade::<T, U, V>(
        &args.strategy_params,
        &args.stop_loss_params,
        &args.take_profit_params,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        args.interval,
        args.quote,
        args.missed_candle_policy,
        true,
        true,
    ))
}

fn get_stats<T: Chromosome, U: Chromosome, V: Chromosome>(
    args: &Params<T, U, V>,
    symbol: &str,
    summary: &TradingSummary,
) -> Result<TradingStats> {
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

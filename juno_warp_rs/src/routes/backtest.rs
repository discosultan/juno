use super::custom_reject;
use anyhow::Result;
use juno_rs::{
    chandler::{candles_to_prices, fill_missing_candles},
    statistics::Statistics,
    stop_loss::StopLossParams,
    storages,
    strategies::*,
    take_profit::TakeProfitParams,
    time::{deserialize_interval, deserialize_timestamp, DAY_MS},
    trading::{trade, MissedCandlePolicy, TradingSummary},
    SymbolExt,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use warp::{reply, Filter, Rejection, Reply};

#[derive(Debug, Deserialize)]
struct Params {
    exchange: String,
    symbols: Vec<String>,
    #[serde(deserialize_with = "deserialize_interval")]
    interval: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    quote: f64,
    strategy_params: StrategyParams,
    stop_loss: StopLossParams,
    take_profit: TakeProfitParams,
    missed_candle_policy: MissedCandlePolicy,
}

#[derive(Serialize)]
struct BacktestResult {
    symbol_stats: HashMap<String, Statistics>,
}

pub fn routes() -> impl Filter<Extract = impl Reply, Error = Rejection> + Clone {
    warp::path("backtest").and(post())
}

fn post() -> impl Filter<Extract = (reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::body::json())
        .and_then(|args: Params| async move { process(args).map_err(|error| custom_reject(error)) })
}

fn process(args: Params) -> Result<reply::Json> {
    let symbol_summaries = args
        .symbols
        .iter()
        .map(|symbol| {
            let summary = backtest(&args, symbol).expect("backtest");
            (symbol.to_owned(), summary) // TODO: Return &String instead.
        })
        .collect::<HashMap<_, _>>();
    let symbol_stats = symbol_summaries
        .iter()
        .map(|(symbol, summary)| {
            let stats = get_stats(&args, symbol, summary).expect("get stats");
            (symbol.to_owned(), stats) // TODO: Return &String instead.
        })
        .collect::<HashMap<_, _>>();

    Ok(reply::json(&BacktestResult { symbol_stats }))
}

fn backtest(args: &Params, symbol: &str) -> Result<TradingSummary> {
    let candles =
        storages::list_candles(&args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trade(
        &args.strategy_params,
        &args.stop_loss,
        &args.take_profit,
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

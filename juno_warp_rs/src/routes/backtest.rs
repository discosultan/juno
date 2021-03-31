use super::custom_reject;
use anyhow::Result;
use juno_rs::{
    chandler,
    statistics::Statistics,
    storages,
    time::{deserialize_timestamp, DAY_MS},
    trading::{trade, TradingParams, TradingSummary},
    SymbolExt,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use warp::{reply, Filter, Rejection, Reply};

#[derive(Debug, Deserialize)]
struct Params {
    exchange: String,
    symbols: Vec<String>,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    quote: f64,
    trading: TradingParams,
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
            let summary = backtest(&args, symbol)?;
            Ok((symbol.to_owned(), summary)) // TODO: Return &String instead.
        })
        .collect::<Result<HashMap<_, _>>>()?;
    let symbol_stats = symbol_summaries
        .iter()
        .map(|(symbol, summary)| {
            let stats = get_stats(&args, symbol, summary)?;
            Ok((symbol.to_owned(), stats)) // TODO: Return &String instead.
        })
        .collect::<Result<_>>()?;

    Ok(reply::json(&BacktestResult { symbol_stats }))
}

fn backtest(args: &Params, symbol: &str) -> Result<TradingSummary> {
    let candles = chandler::list_candles(
        &args.exchange,
        symbol,
        args.trading.trader.interval,
        args.start,
        args.end,
    )?;
    let exchange_info = storages::get_exchange_info(&args.exchange)?;

    Ok(trade(
        &args.trading,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        args.quote,
        true,
        true,
    ))
}

fn get_stats(args: &Params, symbol: &str, summary: &TradingSummary) -> Result<Statistics> {
    let stats_interval = DAY_MS;
    let start = args.start;
    let end = args.end;

    // Stats base.
    let stats_candles =
        chandler::list_candles_fill_missing(&args.exchange, symbol, stats_interval, start, end)?;

    // Stats quote (optional).
    let stats_fiat_candles =
        chandler::list_candles_fill_missing("coinbase", "btc-eur", stats_interval, start, end)?;

    // let stats_quote_prices = None;
    let stats_quote_prices = Some(chandler::candles_to_prices(&stats_fiat_candles, None));
    let stats_base_prices =
        chandler::candles_to_prices(&stats_candles, stats_quote_prices.as_deref());

    let stats = Statistics::compose(
        &summary,
        &stats_base_prices,
        stats_quote_prices.as_deref(),
        stats_interval,
    );

    Ok(stats)
}

use super::custom_reject;
use anyhow::{Error, Result};
use futures::future::{try_join, try_join_all};
use juno_rs::{
    candles,
    statistics::Statistics,
    storage,
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
struct BacktestResult<'a> {
    symbol_stats: HashMap<&'a str, Statistics>,
}

pub fn routes() -> impl Filter<Extract = impl Reply, Error = Rejection> + Clone {
    warp::path("backtest").and(post())
}

fn post() -> impl Filter<Extract = (reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::body::json())
        .and_then(|args: Params| async move {
            process(args).await.map_err(|error| custom_reject(error))
        })
}

async fn process(args: Params) -> Result<reply::Json> {
    let symbol_summary_tasks =
        args.symbols
            .iter()
            .map(|symbol| (symbol, &args))
            .map(|(symbol, args)| async move {
                let summary = backtest(&args, symbol).await?;
                Ok::<_, Error>((symbol, summary))
            });
    let symbol_summaries = try_join_all(symbol_summary_tasks).await?;

    let symbol_stat_tasks = symbol_summaries
        .iter()
        .map(|(symbol, summary)| (symbol, summary, &args))
        .map(|(symbol, summary, args)| async move {
            let stats = get_stats(&args, symbol, summary).await?;
            Ok::<_, Error>((symbol.as_ref(), stats))
        });
    let symbol_stats = try_join_all(symbol_stat_tasks).await?.into_iter().collect();

    Ok(reply::json(&BacktestResult { symbol_stats }))
}

async fn backtest(args: &Params, symbol: &str) -> Result<TradingSummary> {
    let candles = candles::list_candles(
        &args.exchange,
        symbol,
        args.trading.trader.interval,
        args.start,
        args.end,
    )
    .await?;
    let interval_offsets = candles::map_interval_offsets();
    let exchange_info = storage::get_exchange_info(&args.exchange)?;

    Ok(trade(
        &args.trading,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        &interval_offsets,
        2,
        args.quote,
        true,
        true,
    ))
}

async fn get_stats(args: &Params, symbol: &str, summary: &TradingSummary) -> Result<Statistics> {
    let stats_interval = DAY_MS;
    let start = args.start;
    let end = args.end;

    // Stats base.
    let stats_candles_task =
        candles::list_candles_fill_missing(&args.exchange, symbol, stats_interval, start, end);

    // Stats quote (optional).
    let stats_fiat_candles_task =
        candles::list_candles_fill_missing("binance", "btc-usdt", stats_interval, start, end);

    let (stats_candles, stats_fiat_candles) =
        try_join(stats_candles_task, stats_fiat_candles_task).await?;

    // let stats_quote_prices = None;
    let stats_quote_prices = Some(candles::candles_to_prices(&stats_fiat_candles, None));
    let stats_base_prices =
        candles::candles_to_prices(&stats_candles, stats_quote_prices.as_deref());

    let stats = Statistics::compose(
        &summary,
        &stats_base_prices,
        stats_quote_prices.as_deref(),
        stats_interval,
    );

    Ok(stats)
}

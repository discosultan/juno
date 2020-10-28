use juno_rs::{fill_missing_candles, prelude::*, storages, Candle};
use serde::Deserialize;
use std::collections::HashMap;
use warp::{Filter, Rejection};

#[derive(Debug, Deserialize)]
struct Params {
    exchange: String,
    #[serde(deserialize_with = "deserialize_interval")]
    interval: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    start: u64,
    #[serde(deserialize_with = "deserialize_timestamp")]
    end: u64,
    symbols: Vec<String>,
}

pub fn route() -> impl Filter<Extract = (warp::reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::path("candles"))
        .and(warp::body::json())
        .map(|args: Params| {
            let symbol_candles = args
                .symbols
                .iter()
                .map(|symbol| {
                    let candles = storages::list_candles(
                        &args.exchange,
                        symbol,
                        args.interval,
                        args.start,
                        args.end,
                    )
                    .unwrap();
                    let candles =
                        fill_missing_candles(args.interval, args.start, args.end, &candles);
                    (symbol, candles)
                })
                .collect::<HashMap<&String, Vec<Candle>>>();

            warp::reply::json(&symbol_candles)
        })
}

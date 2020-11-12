use super::custom_reject;
use anyhow::Result;
use juno_rs::{chandler::fill_missing_candles, prelude::*, storages, Candle};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use warp::{reject::Reject, reply::Json, Filter, Rejection};

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

#[derive(Debug, Serialize)]
struct MissingCandles {
    message: String,
}

impl Reject for MissingCandles {}

pub fn route() -> impl Filter<Extract = (Json,), Error = Rejection> + Clone {
    warp::post()
        .and(warp::path("candles"))
        .and(warp::body::json())
        .and_then(|args: Params| async move {
            let symbol_candles_result = args
                .symbols
                .iter()
                .map(|symbol| {
                    let candles = storages::list_candles(
                        &args.exchange,
                        symbol,
                        args.interval,
                        args.start,
                        args.end,
                    )?;
                    let candles =
                        fill_missing_candles(args.interval, args.start, args.end, &candles)?;
                    Ok((symbol, candles))
                })
                .collect::<Result<HashMap<&String, Vec<Candle>>>>();

            match symbol_candles_result {
                Ok(symbol_candles) => Ok(warp::reply::json(&symbol_candles)),
                Err(msg) => Err(custom_reject(msg)),
            }
        })
}

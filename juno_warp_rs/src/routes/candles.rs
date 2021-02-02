use super::custom_reject;
use anyhow::Result;
use juno_rs::{
    chandler::fill_missing_candles,
    primitives::{Interval, Timestamp},
    storages, Candle,
};
use serde::Deserialize;
use std::collections::HashMap;
use warp::{body, reply, Filter, Rejection, Reply};

#[derive(Debug, Deserialize)]
struct Params {
    exchange: String,
    interval: Interval,
    start: Timestamp,
    end: Timestamp,
    symbols: Vec<String>,
}

pub fn routes() -> impl Filter<Extract = impl Reply, Error = Rejection> + Clone {
    warp::path("candles").and(post())
}

fn post() -> impl Filter<Extract = (reply::Json,), Error = Rejection> + Clone {
    warp::post()
        .and(body::json())
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
                Ok(symbol_candles) => Ok(reply::json(&symbol_candles)),
                Err(error) => Err(custom_reject(error)),
            }
        })
}

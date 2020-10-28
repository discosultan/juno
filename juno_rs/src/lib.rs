pub mod ffi;
pub mod filters;
pub mod genetics;
pub mod indicators;
pub mod itertools;
pub mod math;
pub mod prelude;
pub mod statistics;
pub mod storages;
pub mod strategies;
pub mod time;
pub mod trading;

pub use crate::{ffi::*, filters::Filters, math::floor_multiple};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

pub trait SymbolExt {
    fn assets(&self) -> (&str, &str);
    fn base_asset(&self) -> &str;
    fn quote_asset(&self) -> &str;
}

impl SymbolExt for str {
    fn assets(&self) -> (&str, &str) {
        let dash_i = dash_index(self);
        (&self[..dash_i], &self[dash_i..])
    }
    fn base_asset(&self) -> &str {
        &self[..dash_index(self)]
    }
    fn quote_asset(&self) -> &str {
        &self[dash_index(self)..]
    }
}

fn dash_index(value: &str) -> usize {
    value.find('-').expect("not a valid symbol")
}

pub fn fill_missing_candles(
    interval: u64,
    start: u64,
    end: u64,
    candles: &[Candle],
) -> Vec<Candle> {
    let start = floor_multiple(start, interval);
    let end = floor_multiple(end, interval);
    let length = ((end - start) / interval) as usize;

    let mut candles_filled = Vec::with_capacity(length);
    let mut current = start;
    let mut prev_candle: Option<&Candle> = None;

    for candle in candles {
        let diff = (candle.time - current) / interval;
        for i in 1..=diff {
            match prev_candle {
                None => panic!("missing candle(s) from start of period; cannot fill"),
                Some(ref c) => candles_filled.push(
                    // Candle {
                    //     time: c.time + i as u64 * interval,
                    //     open: c.open,
                    //     high: c.high,
                    //     low: c.low,
                    //     close: c.close,
                    //     volume: c.volume,
                    // }
                    Candle {
                        time: c.time + i as u64 * interval,
                        open: c.close,
                        high: c.close,
                        low: c.close,
                        close: c.close,
                        volume: 0.0,
                    },
                ),
            }
            current += interval;
        }

        candles_filled.push(*candle);
        current += interval;

        prev_candle = Some(candle);
    }

    if current != end {
        panic!("missing candle(s) from end of period; cannot fill");
    }
    assert_eq!(candles_filled.len(), length);

    candles_filled
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Advice {
    None,
    Long,
    Short,
    Liquidate,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[repr(C)]
pub struct BorrowInfo {
    pub daily_interest_rate: f64,
    pub limit: f64,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[repr(C)]
pub struct Candle {
    #[serde(deserialize_with = "deserialize_timestamp")]
    pub time: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[repr(C)]
pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

#[derive(Deserialize, Serialize)]
pub struct ExchangeInfo {
    pub fees: HashMap<String, Fees>,
    pub filters: HashMap<String, Filters>,
    pub borrow_info: HashMap<String, HashMap<String, BorrowInfo>>,
}

#![allow(dead_code)]

pub mod common;
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
pub mod traders;
pub mod trading;

pub use crate::{
    common::{Advice, BorrowInfo, Candle, Fees},
    filters::Filters,
    ffi::*,
};
use crate::math::floor_multiple;

pub fn fill_missing_candles(interval: u64, start: u64, end: u64, candles: &[Candle]) -> Vec<Candle> {
    let start = floor_multiple(start, interval);
    let end = floor_multiple(end, interval);
    let length = ((end - start) / interval) as usize;

    let mut candles_filled = Vec::with_capacity(length);
    let mut current = start;
    let mut prev_candle: Option<&Candle> = None;

    for candle in candles {
        let mut diff = (candle.time - current) / interval;
        for i in 1..=diff {
            diff -= 1;
            match prev_candle {
                None => panic!("missing first candle in period; cannot fill"),
                Some(ref c) => candles_filled.push(Candle {
                    time: c.time + i as u64 * interval,
                    open: c.open,
                    high: c.high,
                    low: c.low,
                    close: c.close,
                    volume: c.volume,
                }),
            }
            current += interval;
        }

        candles_filled.push(*candle);
        current += interval;

        prev_candle = Some(candle);
    }

    assert_eq!(candles_filled.len(), length);
    candles_filled
}

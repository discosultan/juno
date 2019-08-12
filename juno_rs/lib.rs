mod agents;
mod filters;
mod indicators;
mod strategies;
mod utils;

use std::slice;

use agents::{backtest, BacktestResult};
// use filters;
use strategies::EmaEmaCx;

#[no_mangle]
pub unsafe extern "C" fn emaemacx(
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    // filters: &Filters,
    quote: f64,
    // short_period: u32,
    // long_period: u32,
    // neg_threshold: f64,
    // pos_threshold: f64,
    // persistence: u32,
) -> BacktestResult {
    // Turn unsafe ptrs to safe references.
    let candles = slice::from_raw_parts(candles, length as usize);
    let fees = &*fees;
    
    (0.0, 0.0, 1.0, 0.0, 0)
}

pub struct Candle {
    time: u64,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    closed: bool,
}

#[derive(Clone, Copy, PartialEq)]
pub enum Advice {
    None,
    Buy,
    Sell,
}

#[derive(Clone, Copy, PartialEq)]
pub enum Trend {
    Unknown,
    Up,
    Down,
}

pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

impl Fees {
    pub fn none() -> Self {
        Fees {
            maker: 0.0,
            taker: 0.0,
        }
    }
}

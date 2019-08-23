mod backtest;
mod common;
mod filters;
mod indicators;
mod strategies;
mod summary;
mod utils;

use std::slice;

pub use common::{Advice, Candle, Fees, Trend};
pub use filters::Filters;
pub use summary::{Position, TradingSummary};
use backtest::{backtest, BacktestResult};
use strategies::{EmaEmaCX, Strategy};

#[no_mangle]
pub unsafe extern "C" fn emaemacx(
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    interval: u64,
    start: u64,
    end: u64,
    quote: f64,
    short_period: u32,
    long_period: u32,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: u32,
) -> BacktestResult {
    let strategy_factory = || EmaEmaCX::new(
        short_period, long_period, neg_threshold, pos_threshold, persistence);
    run_test(strategy_factory, candles, length, fees, filters, interval, start, end, quote)
}

unsafe fn run_test<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    interval: u64,
    start: u64,
    end: u64,
    quote: f64,
) -> BacktestResult {
    // Turn unsafe ptrs to safe references.
    let candles = slice::from_raw_parts(candles, length as usize);
    let fees = &*fees;
    let filters = &*filters;

    let res = backtest(strategy_factory, candles, fees, filters, interval, start, end, quote);
    res
}

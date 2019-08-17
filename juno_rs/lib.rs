mod agents;
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
use agents::{backtest, BacktestResult};
use strategies::{EmaEmaCX, Strategy};

#[no_mangle]
pub unsafe extern "C" fn emaemacx(
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    quote: f64,
    short_period: u32,
    long_period: u32,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: u32,
) -> BacktestResult {
    let strategy = EmaEmaCX::new(
        short_period, long_period, neg_threshold, pos_threshold, persistence);
    run_test(strategy, candles, length, fees, filters, quote)
}

unsafe fn run_test<T: Strategy>(
    mut strategy: T,
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    quote: f64,
) -> BacktestResult {
    // Turn unsafe ptrs to safe references.
    let candles = slice::from_raw_parts(candles, length as usize);
    let fees = &*fees;
    let filters = &*filters;

    // println!("{:?}", candles);
    // println!("{:?}", fees);
    // println!("{:?}", filters);

    // (0.0, 0.0, 1.0, 0.0, 0)

    backtest(strategy, candles, fees, filters, quote)
}

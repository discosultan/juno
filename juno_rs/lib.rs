#![allow(dead_code)]

mod backtest;
mod common;
mod filters;
mod indicators;
mod math;
mod strategies;
mod trading;
mod utils;

use std::ffi::CStr;
use std::os::raw::c_char;
use std::slice;
use backtest::{backtest, BacktestResult};
use indicators::{Ema, Ema2, MA, Sma, Smma};
use strategies::{MAMACX, Strategy};
pub use common::{Advice, Candle, Fees, Trend};
pub use filters::Filters;
pub use trading::{Position, TradingContext, TradingSummary};

#[no_mangle]
pub unsafe extern "C" fn mamacx(
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    trailing_stop: f64,
    short_period: u32,
    long_period: u32,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: u32,
    short_ma: *const c_char,
    long_ma: *const c_char,
) -> BacktestResult {
    let short_ma = CStr::from_ptr(short_ma).to_bytes();
    let long_ma = CStr::from_ptr(long_ma).to_bytes();
    match (short_ma, long_ma) {
        (b"ema",  b"ema")  => run_mamacx_test::<Ema, Ema>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"ema",  b"ema2") => run_mamacx_test::<Ema, Ema2> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"ema",  b"sma")  => run_mamacx_test::<Ema, Sma>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"ema",  b"smma") => run_mamacx_test::<Ema, Smma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"ema2", b"ema")  => run_mamacx_test::<Ema2, Ema> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"ema2", b"ema2") => run_mamacx_test::<Ema2, Ema2>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"ema2", b"sma")  => run_mamacx_test::<Ema2, Sma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"ema2", b"smma") => run_mamacx_test::<Ema2, Smma>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"sma",  b"ema")  => run_mamacx_test::<Sma, Ema>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"sma",  b"ema2") => run_mamacx_test::<Sma, Ema2> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"sma",  b"sma")  => run_mamacx_test::<Sma, Sma>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"sma",  b"smma") => run_mamacx_test::<Sma, Smma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"smma", b"ema")  => run_mamacx_test::<Smma, Ema> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"smma", b"ema2") => run_mamacx_test::<Smma, Ema2>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"smma", b"sma")  => run_mamacx_test::<Smma, Sma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (b"smma", b"smma") => run_mamacx_test::<Smma, Smma>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        _ => panic!()
    }
}

unsafe fn run_mamacx_test<TShort: MA, TLong: MA>(
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    trailing_stop: f64,
    short_period: u32,
    long_period: u32,   
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: u32,
) -> BacktestResult {
    let strategy_factory = || {
        MAMACX::new(
            TShort::new(short_period),
            TLong::new(long_period),
            neg_threshold,
            pos_threshold,
            persistence,
        )
    };
    run_test(
        candles,
        length,
        fees,
        filters,
        interval,
        quote,
        missed_candle_policy,
        trailing_stop,
        strategy_factory,
    )
}

unsafe fn run_test<TF: Fn() -> TS, TS: Strategy>(
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    trailing_stop: f64,
    strategy_factory: TF,
) -> BacktestResult {
    // Turn unsafe ptrs to safe references.
    let candles = slice::from_raw_parts(candles, length as usize);
    let fees = &*fees;
    let filters = &*filters;

    // println!("{:?}", fees);
    // println!("{:?}", filters);

    backtest(
        strategy_factory,
        candles,
        fees,
        filters,
        interval,
        quote,
        missed_candle_policy,
        trailing_stop,
    )
}

#![allow(dead_code)]

mod backtest;
mod common;
mod filters;
mod indicators;
mod math;
mod strategies;
mod trading;
mod utils;

use std::slice;
use backtest::{backtest, BacktestResult};
use indicators::{Ema, Ema2, MA, Sma, Smma};
use strategies::{MAMACX, Strategy};
pub use common::{Advice, Candle, Fees, Trend};
pub use filters::Filters;
pub use trading::{Position, TradingContext, TradingSummary};

#[repr(C)]
pub struct Payload {
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
    short_ma: u32,
    long_ma: u32,
}

#[no_mangle]
pub unsafe extern "C" fn mamacx_multiple(
    payloads: *const Payload,
    length: u32,
) -> Vec<BacktestResult> {
    let payloads = slice::from_raw_parts(payloads, length as usize);
    let mut result = Vec::with_capacity(length as usize);
    for p in payloads {
        result.push(mamacx(
            p.candles,
            p.length,
            p.fees,
            p.filters,
            p.interval,
            p.quote,
            p.missed_candle_policy,
            p.trailing_stop,
            p.short_period,
            p.long_period,
            p.neg_threshold,
            p.pos_threshold,
            p.persistence,
            p.short_period,
            p.long_period,
        ));
    }
    result
}

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
    short_ma: u32,
    long_ma: u32,
) -> BacktestResult {
    match (short_ma, long_ma) {
        (0, 0) => run_mamacx_test::<Ema, Ema>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (0, 1) => run_mamacx_test::<Ema, Ema2> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (0, 2) => run_mamacx_test::<Ema, Sma>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (0, 3) => run_mamacx_test::<Ema, Smma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (1, 0) => run_mamacx_test::<Ema2, Ema> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (1, 1) => run_mamacx_test::<Ema2, Ema2>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (1, 2) => run_mamacx_test::<Ema2, Sma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (1, 3) => run_mamacx_test::<Ema2, Smma>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (2, 0) => run_mamacx_test::<Sma, Ema>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (2, 1) => run_mamacx_test::<Sma, Ema2> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (2, 2) => run_mamacx_test::<Sma, Sma>  (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (2, 3) => run_mamacx_test::<Sma, Smma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (3, 0) => run_mamacx_test::<Smma, Ema> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (3, 1) => run_mamacx_test::<Smma, Ema2>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (3, 2) => run_mamacx_test::<Smma, Sma> (candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
        (3, 3) => run_mamacx_test::<Smma, Smma>(candles, length, fees, filters, interval, quote, missed_candle_policy, trailing_stop, short_period, long_period, neg_threshold, pos_threshold, persistence),
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

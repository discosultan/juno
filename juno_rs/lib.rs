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
pub struct AnalysisInfo {
    base_fiat_candles: *const Candle,
    base_fiat_candles_length: u32,
    portfolio_candles: *const Candle,
    portfolio_candles_length: u32,
    benchmark_g_returns: *const f64,
    benchmark_g_returns_length: u32,
}

#[repr(C)]
pub struct TradingInfo {
    candles: *const Candle,
    candles_length: u32,
    fees: *const Fees,
    filters: *const Filters,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    trailing_stop: f64,
}

#[repr(C)]
pub struct MAMACXInfo {
    short_period: u32,
    long_period: u32,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: u32,
    short_ma: u32,
    long_ma: u32,
}

#[no_mangle]
pub unsafe extern "C" fn mamacx(
    analysis_info: *const AnalysisInfo,
    trading_info: *const TradingInfo,
    mamacx_info: *const MAMACXInfo,
) -> BacktestResult {
    let mamacx_info = &*mamacx_info;
    match (mamacx_info.short_ma, mamacx_info.long_ma) {
        (0, 0) => run_mamacx_test::<Ema, Ema>  (analysis_info, trading_info, mamacx_info),
        (0, 1) => run_mamacx_test::<Ema, Ema2> (analysis_info, trading_info, mamacx_info),
        (0, 2) => run_mamacx_test::<Ema, Sma>  (analysis_info, trading_info, mamacx_info),
        (0, 3) => run_mamacx_test::<Ema, Smma> (analysis_info, trading_info, mamacx_info),
        (1, 0) => run_mamacx_test::<Ema2, Ema> (analysis_info, trading_info, mamacx_info),
        (1, 1) => run_mamacx_test::<Ema2, Ema2>(analysis_info, trading_info, mamacx_info),
        (1, 2) => run_mamacx_test::<Ema2, Sma> (analysis_info, trading_info, mamacx_info),
        (1, 3) => run_mamacx_test::<Ema2, Smma>(analysis_info, trading_info, mamacx_info),
        (2, 0) => run_mamacx_test::<Sma, Ema>  (analysis_info, trading_info, mamacx_info),
        (2, 1) => run_mamacx_test::<Sma, Ema2> (analysis_info, trading_info, mamacx_info),
        (2, 2) => run_mamacx_test::<Sma, Sma>  (analysis_info, trading_info, mamacx_info),
        (2, 3) => run_mamacx_test::<Sma, Smma> (analysis_info, trading_info, mamacx_info),
        (3, 0) => run_mamacx_test::<Smma, Ema> (analysis_info, trading_info, mamacx_info),
        (3, 1) => run_mamacx_test::<Smma, Ema2>(analysis_info, trading_info, mamacx_info),
        (3, 2) => run_mamacx_test::<Smma, Sma> (analysis_info, trading_info, mamacx_info),
        (3, 3) => run_mamacx_test::<Smma, Smma>(analysis_info, trading_info, mamacx_info),
        _ => panic!(
            "Moving average ({}, {}) not implemented!",
            mamacx_info.short_ma,
            mamacx_info.long_ma
        ),
    }
}

unsafe fn run_mamacx_test<TShort: MA, TLong: MA>(
    analysis_info: *const AnalysisInfo,
    trading_info: *const TradingInfo,
    mamacx_info: &MAMACXInfo,
) -> BacktestResult {
    let strategy_factory = || {
        MAMACX::new(
            TShort::new(mamacx_info.short_period),
            TLong::new(mamacx_info.long_period),
            mamacx_info.neg_threshold,
            mamacx_info.pos_threshold,
            mamacx_info.persistence,
        )
    };
    run_test(analysis_info, trading_info, strategy_factory)
}

unsafe fn run_test<TF: Fn() -> TS, TS: Strategy>(
    analysis_info: *const AnalysisInfo,
    trading_info: *const TradingInfo,
    strategy_factory: TF,
) -> BacktestResult {
    // Turn unsafe ptrs to safe references.
    let _analysis_info = &*analysis_info;
    let trader_info = &*trading_info;
    let candles = slice::from_raw_parts(trader_info.candles, trader_info.candles_length as usize);
    let fees = &*trader_info.fees;
    let filters = &*trader_info.filters;

    // println!("{:?}", fees);
    // println!("{:?}", filters);

    backtest(
        strategy_factory,
        candles,
        fees,
        filters,
        trader_info.interval,
        trader_info.quote,
        trader_info.missed_candle_policy,
        trader_info.trailing_stop,
    )
}

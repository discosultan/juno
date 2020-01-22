#![allow(dead_code)]

mod analyse;
mod trade;
mod common;
mod filters;
mod indicators;
mod math;
mod strategies;
mod trading;
mod utils;

use std::slice;
use crate::{
    analyse::analyse,
    indicators::{Ema, Ema2, MA, Sma, Smma},
    strategies::{Macd, MAMACX, Strategy},
    trade::trade,
};
pub use crate::{
    common::{Advice, Candle, Fees, Trend},
    filters::Filters,
    trading::{Position, TradingContext, TradingSummary},
};

#[no_mangle]
pub unsafe extern "C" fn macd(
    trading_info: *const TradingInfo,
    macd_info: *const MacdInfo,
    analysis_info: *const AnalysisInfo,
) -> Result {
    let macd_info = &*macd_info;
    let strategy_factory = || {
        Macd::new(
            macd_info.short_period,
            macd_info.long_period,
            macd_info.signal_period,
            macd_info.persistence,
        )
    };
    run_test(trading_info, strategy_factory, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn mamacx(
    trading_info: *const TradingInfo,
    mamacx_info: *const MAMACXInfo,
    analysis_info: *const AnalysisInfo,
) -> Result {
    let mamacx_info = &*mamacx_info;
    match (mamacx_info.short_ma, mamacx_info.long_ma) {
        (0, 0) => run_mamacx_test::<Ema, Ema>  (trading_info, mamacx_info, analysis_info),
        (0, 1) => run_mamacx_test::<Ema, Ema2> (trading_info, mamacx_info, analysis_info),
        (0, 2) => run_mamacx_test::<Ema, Sma>  (trading_info, mamacx_info, analysis_info),
        (0, 3) => run_mamacx_test::<Ema, Smma> (trading_info, mamacx_info, analysis_info),
        (1, 0) => run_mamacx_test::<Ema2, Ema> (trading_info, mamacx_info, analysis_info),
        (1, 1) => run_mamacx_test::<Ema2, Ema2>(trading_info, mamacx_info, analysis_info),
        (1, 2) => run_mamacx_test::<Ema2, Sma> (trading_info, mamacx_info, analysis_info),
        (1, 3) => run_mamacx_test::<Ema2, Smma>(trading_info, mamacx_info, analysis_info),
        (2, 0) => run_mamacx_test::<Sma, Ema>  (trading_info, mamacx_info, analysis_info),
        (2, 1) => run_mamacx_test::<Sma, Ema2> (trading_info, mamacx_info, analysis_info),
        (2, 2) => run_mamacx_test::<Sma, Sma>  (trading_info, mamacx_info, analysis_info),
        (2, 3) => run_mamacx_test::<Sma, Smma> (trading_info, mamacx_info, analysis_info),
        (3, 0) => run_mamacx_test::<Smma, Ema> (trading_info, mamacx_info, analysis_info),
        (3, 1) => run_mamacx_test::<Smma, Ema2>(trading_info, mamacx_info, analysis_info),
        (3, 2) => run_mamacx_test::<Smma, Sma> (trading_info, mamacx_info, analysis_info),
        (3, 3) => run_mamacx_test::<Smma, Smma>(trading_info, mamacx_info, analysis_info),
        _ => panic!(
            "Moving average ({}, {}) not implemented!",
            mamacx_info.short_ma,
            mamacx_info.long_ma
        ),
    }
}

unsafe fn run_mamacx_test<TShort: MA, TLong: MA>(
    trading_info: *const TradingInfo,
    mamacx_info: &MAMACXInfo,
    analysis_info: *const AnalysisInfo,
) -> Result {
    let strategy_factory = || {
        MAMACX::new(
            TShort::new(mamacx_info.short_period),
            TLong::new(mamacx_info.long_period),
            mamacx_info.neg_threshold,
            mamacx_info.pos_threshold,
            mamacx_info.persistence,
        )
    };
    run_test(trading_info, strategy_factory, analysis_info)
}

unsafe fn run_test<TF: Fn() -> TS, TS: Strategy>(
    trading_info: *const TradingInfo,
    strategy_factory: TF,
    analysis_info: *const AnalysisInfo,
) -> Result {
    // Trading.
    // Turn unsafe ptrs to safe references.
    let trading_info = &*trading_info;
    let candles = slice::from_raw_parts(trading_info.candles, trading_info.candles_length as usize);
    let fees = &*trading_info.fees;
    let filters = &*trading_info.filters;

    let trading_result = trade(
        strategy_factory,
        candles,
        fees,
        filters,
        trading_info.interval,
        trading_info.quote,
        trading_info.missed_candle_policy,
        trading_info.trailing_stop,
    );

    // Analysis.
    let analysis_info = &*analysis_info;
    let quote_fiat_daily = slice::from_raw_parts(
        analysis_info.quote_fiat_daily, 
        analysis_info.quote_fiat_daily_length as usize
    );
    let base_fiat_daily = slice::from_raw_parts(
        analysis_info.base_fiat_daily, 
        analysis_info.base_fiat_daily_length as usize
    );
    let benchmark_g_returns = slice::from_raw_parts(
        analysis_info.benchmark_g_returns,
        analysis_info.benchmark_g_returns_length as usize
    );

    let analysis_result = analyse(
        quote_fiat_daily,
        base_fiat_daily,
        benchmark_g_returns,
        &trading_result
    );

    // Combine.
    (
        analysis_result.0,
        // trading_result.profit,
        // trading_result.mean_drawdown,
        // trading_result.max_drawdown,
        // trading_result.mean_position_profit,
        // trading_result.mean_position_duration,
        // trading_result.num_positions_in_profit,
        // trading_result.num_positions_in_loss,
    )
}

pub type Result = (f64, ); // (f64, f64, f64, f64, f64, u64, u32, u32);

#[repr(C)]
pub struct AnalysisInfo {
    quote_fiat_daily: *const Candle,
    quote_fiat_daily_length: u32,
    base_fiat_daily: *const f64,
    base_fiat_daily_length: u32,
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
pub struct MacdInfo {
    short_period: u32,
    long_period: u32,
    signal_period: u32,
    persistence: u32,
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

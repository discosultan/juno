use crate::{
    statistics, stop_loss,
    strategies::{self, Signal},
    take_profit,
    time::DAY_MS,
    trading::trade,
    BorrowInfo, Candle, Fees, Filters,
};
use std::slice;

#[no_mangle]
pub unsafe extern "C" fn singlema(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::SingleMAParams,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    run_test::<strategies::SingleMA>(trading_info, strategy_info, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn doublema(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::DoubleMAParams,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    run_test::<strategies::DoubleMA>(trading_info, strategy_info, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn doublema2(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::DoubleMA2Params,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    run_test::<strategies::DoubleMA2>(trading_info, strategy_info, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn triplema(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::TripleMAParams,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    run_test::<strategies::TripleMA>(trading_info, strategy_info, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn fourweekrule(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::FourWeekRuleParams,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    run_test::<strategies::FourWeekRule>(trading_info, strategy_info, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn macd(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::MacdParams,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    run_test::<strategies::Macd>(trading_info, strategy_info, analysis_info)
}

unsafe fn run_test<T: Signal>(
    trading_info: *const TradingInfo,
    strategy_params: *const T::Params,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    // Trading.
    // Turn unsafe ptrs to safe references.
    let trading_info = &*trading_info;
    let strategy_params = &*strategy_params;
    let candles = slice::from_raw_parts(trading_info.candles, trading_info.candles_length as usize);
    let fees = &*trading_info.fees;
    let filters = &*trading_info.filters;
    let borrow_info = &*trading_info.borrow_info;
    let trading_summary = trade::<T, stop_loss::Legacy, take_profit::Legacy>(
        strategy_params,
        &stop_loss::LegacyParams {
            threshold: trading_info.stop_loss,
            trail: trading_info.trail_stop_loss,
        },
        &take_profit::LegacyParams {
            threshold: trading_info.take_profit,
        },
        candles,
        fees,
        filters,
        borrow_info,
        trading_info.margin_multiplier,
        trading_info.interval,
        trading_info.quote,
        trading_info.missed_candle_policy,
        trading_info.long,
        trading_info.short,
    );

    // Analysis.
    let analysis_info = &*analysis_info;
    let quote_fiat_prices = slice::from_raw_parts(
        analysis_info.quote_fiat_prices,
        analysis_info.quote_fiat_prices_length as usize,
    );
    let base_fiat_prices = slice::from_raw_parts(
        analysis_info.base_fiat_prices,
        analysis_info.base_fiat_prices_length as usize,
    );
    // let benchmark_g_returns = slice::from_raw_parts(
    //     analysis_info.benchmark_g_returns,
    //     analysis_info.benchmark_g_returns_length as usize,
    // );

    let stats = statistics::analyse(
        &trading_summary,
        &base_fiat_prices,
        Some(&quote_fiat_prices),
        // benchmark_g_returns,
        DAY_MS,
    );

    // Combine.
    FitnessValues(
        stats.sharpe_ratio,
        // stats.sortino_ratio,
        // trading_summary.profit,
        // trading_summary.mean_drawdown,
        // trading_summary.max_drawdown,
        // trading_summary.mean_position_profit,
        // trading_summary.mean_position_duration,
        // trading_summary.num_positions_in_profit,
        // trading_summary.num_positions_in_loss,
    )
}

#[repr(C)]
pub struct FitnessValues(f64); // (f64, f64, f64, f64, f64, u64, u32, u32);

#[repr(C)]
pub struct AnalysisInfo {
    quote_fiat_prices: *const f64,
    quote_fiat_prices_length: u32,
    base_fiat_prices: *const f64,
    base_fiat_prices_length: u32,
    benchmark_g_returns: *const f64,
    benchmark_g_returns_length: u32,
}

#[repr(C)]
pub struct TradingInfo {
    candles: *const Candle,
    candles_length: u32,
    fees: *const Fees,
    filters: *const Filters,
    borrow_info: *const BorrowInfo,
    margin_multiplier: u32,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    stop_loss: f64,
    trail_stop_loss: bool,
    take_profit: f64,
    long: bool,
    short: bool,
}

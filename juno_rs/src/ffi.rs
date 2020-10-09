use crate::{
    statistics,
    strategies::{self, Signal},
    time::DAY_MS,
    traders::trade,
    BorrowInfo, Candle, Fees, Filters,
};
use std::slice;

#[no_mangle]
pub unsafe extern "C" fn singlema(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::SingleMAParams,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    // run_test::<strategies::SingleMA>(trading_info, strategy_info, analysis_info)
    // TODO: Temp.
    let strategy_info = &*strategy_info;
    let params = strategies::SigParams::<strategies::SingleMAParams> {
        sig_params: strategies::SingleMAParams {
            ma: strategy_info.ma,
            period: strategy_info.period,
        },
        persistence: 0,
    };
    let strategy_info = &params;
    run_test::<strategies::Sig<strategies::SingleMA>>(trading_info, strategy_info, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn doublema(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::DoubleMAParams,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    // run_test::<strategies::DoubleMA>(trading_info, strategy_info, analysis_info)
    // TODO: Temp.
    let strategy_info = &*strategy_info;
    let params = strategies::SigParams::<strategies::DoubleMAParams> {
        sig_params: strategies::DoubleMAParams {
            short_ma: strategy_info.short_ma,
            long_ma: strategy_info.long_ma,
            periods: strategy_info.periods,
        },
        persistence: 0,
    };
    let strategy_info = &params;
    run_test::<strategies::Sig<strategies::DoubleMA>>(trading_info, strategy_info, analysis_info)
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
    // run_test::<strategies::Macd>(trading_info, strategy_info, analysis_info)
    // TODO: Temp.
    let strategy_info = &*strategy_info;
    let params = strategies::SigParams::<strategies::MacdParams> {
        sig_params: strategies::MacdParams {
            periods: strategy_info.periods,
            signal_period: strategy_info.signal_period,
            persistence: strategy_info.persistence,
        },
        persistence: strategy_info.persistence,
    };
    let strategy_info = &params;
    run_test::<strategies::Sig<strategies::Macd>>(trading_info, strategy_info, analysis_info)
}

#[no_mangle]
pub unsafe extern "C" fn doublema2(
    trading_info: *const TradingInfo,
    strategy_info: *const strategies::DoubleMA2Params,
    analysis_info: *const AnalysisInfo,
) -> FitnessValues {
    // run_test::<strategies::DuobleMA2>(trading_info, strategy_info, analysis_info)
    // TODO: Temp.
    let strategy_info = &*strategy_info;
    let params = strategies::SigParams::<strategies::DoubleMA2Params> {
        sig_params: strategies::DoubleMA2Params {
            short_ma: strategy_info.short_ma,
            long_ma: strategy_info.long_ma,
            periods: strategy_info.periods,
            neg_threshold: strategy_info.neg_threshold,
            pos_threshold: strategy_info.pos_threshold,
        },
        persistence: 0,
    };
    let strategy_info = &params;
    run_test::<strategies::Sig<strategies::DoubleMA2>>(trading_info, strategy_info, analysis_info)
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
    let trading_result = trade::<T>(
        strategy_params,
        candles,
        fees,
        filters,
        borrow_info,
        trading_info.margin_multiplier,
        trading_info.interval,
        trading_info.quote,
        trading_info.missed_candle_policy,
        trading_info.stop_loss,
        trading_info.trail_stop_loss,
        trading_info.take_profit,
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
    let benchmark_g_returns = slice::from_raw_parts(
        analysis_info.benchmark_g_returns,
        analysis_info.benchmark_g_returns_length as usize,
    );

    let stats = statistics::analyse(
        &base_fiat_prices,
        Some(&quote_fiat_prices),
        benchmark_g_returns,
        &trading_result,
        DAY_MS,
    );

    // Combine.
    FitnessValues(
        stats.sharpe_ratio,
        // stats.sortino_ratio,
        // trading_result.profit,
        // trading_result.mean_drawdown,
        // trading_result.max_drawdown,
        // trading_result.mean_position_profit,
        // trading_result.mean_position_duration,
        // trading_result.num_positions_in_profit,
        // trading_result.num_positions_in_loss,
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

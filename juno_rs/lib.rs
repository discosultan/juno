#![allow(dead_code)]

pub mod common;
pub mod filters;
pub mod indicators;
pub mod math;
pub mod statistics;
pub mod strategies;
pub mod trade;
pub mod trading;

pub use crate::{
    common::{Advice, BorrowInfo, Candle, Fees},
    filters::Filters,
    trading::{LongPosition, ShortPosition, TradingSummary},
};
use crate::{
    statistics::analyse,
    strategies::{Macd, MacdRsi, Strategy, MAMACX},
    trade::trade,
};
use std::slice;
use std::mem;

#[repr(C)]
#[derive(Debug)]
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
    population: *const Individual<MAMACXInfo>,
    fitnesses: *mut FitnessValues,
    length: u32,
) {
    let bar = slice::from_raw_parts(population, length as usize);
    let foo = slice::from_raw_parts_mut(fitnesses, length as usize);
    println!("TUSSUUUUUUUUU {}", length);
    println!("{:?}", &*bar[0].strategy_info);
    println!("sizeof {}", mem::size_of::<MAMACXInfo>());
    let strategy_factory = |strategy_info: &MAMACXInfo| {
        println!("{:?}", strategy_info);
        MAMACX::new(
            strategy_info.short_period,
            strategy_info.long_period,
            strategy_info.neg_threshold,
            strategy_info.pos_threshold,
            strategy_info.persistence,
            strategy_info.short_ma,
            strategy_info.long_ma,
        )
    };
    process_population(population, fitnesses, length, strategy_factory);
}

#[repr(C)]
pub struct FourWeekRuleInfo {
    period: u32,
    ma: u32,
    ma_period: u32,
    mid_trend_policy: u32,
}

#[no_mangle]
pub unsafe extern "C" fn fourweekrule(
    population: *const Individual<FourWeekRuleInfo>,
    fitnesses: *mut FitnessValues,
    length: u32,
) {
    println!("TUSSUUUUUUUUUMAHL");
    let strategy_factory = |strategy_info: &FourWeekRuleInfo| {
        strategies::FourWeekRule::new(
            strategy_info.period,
            strategy_info.ma,
            strategy_info.ma_period,
            strategy_info.mid_trend_policy,
        )
    };
    process_population(population, fitnesses, length, strategy_factory);
}

#[repr(C)]
pub struct SingleMAInfo {
    ma: u32,
    period: u32,
    persistence: u32,
}

#[no_mangle]
pub unsafe extern "C" fn singlema(
    population: *const Individual<SingleMAInfo>,
    fitnesses: *mut FitnessValues,
    length: u32,
) {
    let strategy_factory = |strategy_info: &SingleMAInfo| {
        strategies::SingleMA::new(
            strategy_info.ma,
            strategy_info.period,
            strategy_info.persistence,
        )
    };
    process_population(population, fitnesses, length, strategy_factory);
}

#[repr(C)]
pub struct DoubleMAInfo {
    short_ma: u32,
    long_ma: u32,
    short_period: u32,
    long_period: u32,
}

#[no_mangle]
pub unsafe extern "C" fn doublema(
    population: *const Individual<DoubleMAInfo>,
    fitnesses: *mut FitnessValues,
    length: u32,
) {
    let strategy_factory = |strategy_info: &DoubleMAInfo| {
        strategies::DoubleMA::new(
            strategy_info.short_ma,
            strategy_info.long_ma,
            strategy_info.short_period,
            strategy_info.long_period,
        )
    };
    process_population(population, fitnesses, length, strategy_factory);
}

#[repr(C)]
pub struct TripleMAInfo {
    short_ma: u32,
    medium_ma: u32,
    long_ma: u32,
    short_period: u32,
    medium_period: u32,
    long_period: u32,
}

#[no_mangle]
pub unsafe extern "C" fn triplema(
    population: *const Individual<TripleMAInfo>,
    fitnesses: *mut FitnessValues,
    length: u32,
) {
    let strategy_factory = |strategy_info: &TripleMAInfo| {
        strategies::TripleMA::new(
            strategy_info.short_ma,
            strategy_info.medium_ma,
            strategy_info.long_ma,
            strategy_info.short_period,
            strategy_info.medium_period,
            strategy_info.long_period,
        )
    };
    process_population(population, fitnesses, length, strategy_factory);
}

#[repr(C)]
pub struct MacdInfo {
    short_period: u32,
    long_period: u32,
    signal_period: u32,
    persistence: u32,
}

#[no_mangle]
pub unsafe extern "C" fn macd(
    population: *const Individual<MacdInfo>,
    fitnesses: *mut FitnessValues,
    length: u32,
) {
    let strategy_factory = |strategy_info: &MacdInfo| {
        Macd::new(
            strategy_info.short_period,
            strategy_info.long_period,
            strategy_info.signal_period,
            strategy_info.persistence,
        )
    };
    process_population(population, fitnesses, length, strategy_factory);
}

#[repr(C)]
pub struct MacdRsiInfo {
    macd_short_period: u32,
    macd_long_period: u32,
    macd_signal_period: u32,
    rsi_period: u32,
    rsi_up_threshold: f64,
    rsi_down_threshold: f64,
    persistence: u32,
}

#[no_mangle]
pub unsafe extern "C" fn macdrsi(
    population: *const Individual<MacdRsiInfo>,
    fitnesses: *mut FitnessValues,
    length: u32,
) {
    let strategy_factory = |strategy_info: &MacdRsiInfo| {
        MacdRsi::new(
            strategy_info.macd_short_period,
            strategy_info.macd_long_period,
            strategy_info.macd_signal_period,
            strategy_info.rsi_period,
            strategy_info.rsi_up_threshold,
            strategy_info.rsi_down_threshold,
            strategy_info.persistence,
        )
    };
    process_population(population, fitnesses, length, strategy_factory);
}

unsafe fn process_population<TF: Fn(&TSI) -> TS, TS: Strategy, TSI>(
    population: *const Individual<TSI>,
    fitnesses: *mut FitnessValues,
    length: u32,
    strategy_factory: TF,
) {
    let population = slice::from_raw_parts(population, length as usize);
    let fitnesses = slice::from_raw_parts_mut(fitnesses, length as usize);
    // TODO: parallelize
    for (i, individual) in population.iter().enumerate() {
        fitnesses[i] = process_individual(individual, &strategy_factory);
    }
}

unsafe fn process_individual<TF: Fn(&TSI) -> TS, TS: Strategy, TSI>(
    individual: &Individual<TSI>,
    strategy_factory: &TF,
) -> FitnessValues {
    // Trading.
    // Turn unsafe ptrs to safe references.
    let candles = slice::from_raw_parts(individual.candles, individual.candles_length as usize);
    let fees = &*individual.fees;
    let filters = &*individual.filters;
    let borrow_info = &*individual.borrow_info;
    let trading_result = trade(
        strategy_factory,
        &*individual.strategy_info,
        candles,
        fees,
        filters,
        borrow_info,
        individual.margin_multiplier,
        individual.interval,
        individual.quote,
        individual.missed_candle_policy,
        individual.stop_loss,
        individual.trail_stop_loss,
        individual.take_profit,
        individual.long,
        individual.short,
    );

    // Analysis.
    let quote_fiat_prices = slice::from_raw_parts(
        individual.quote_fiat_prices,
        individual.quote_fiat_prices_length as usize,
    );
    let base_fiat_prices = slice::from_raw_parts(
        individual.base_fiat_prices,
        individual.base_fiat_prices_length as usize,
    );
    let benchmark_g_returns = slice::from_raw_parts(
        individual.benchmark_g_returns,
        individual.benchmark_g_returns_length as usize,
    );
    let stats = analyse(
        quote_fiat_prices,
        base_fiat_prices,
        benchmark_g_returns,
        &trading_result,
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
#[derive(Debug)]
pub struct FitnessValues(f64); // (f64, f64, f64, f64, f64, u64, u32, u32);

#[repr(C)]
#[derive(Debug)]
pub struct Individual<T> {
    // Analysis.
    quote_fiat_prices: *const f64,
    quote_fiat_prices_length: u32,
    base_fiat_prices: *const f64,
    base_fiat_prices_length: u32,
    benchmark_g_returns: *const f64,
    benchmark_g_returns_length: u32,
    // Trading.
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
    // Strategy.
    strategy_info: *const T,
}

// const double* quote_fiat_prices;
// uint32_t quote_fiat_prices_length;
// const double* base_fiat_prices;
// uint32_t base_fiat_prices_length;
// const double* benchmark_g_returns;
// uint32_t benchmark_g_returns_length;
// const Candle* candles;
// uint32_t candles_length;
// const Fees* fees;
// const Filters* filters;
// const BorrowInfo* borrow_info;
// uint32_t margin_multiplier;
// uint64_t interval;
// double quote;
// uint32_t missed_candle_policy;
// double stop_loss;
// bool trail_stop_loss;
// double take_profit;
// bool long_;
// bool short_;
// const void* strategy_info;


#![allow(dead_code)]

mod backtest;
mod common;
mod filters;
mod indicators;
mod math;
mod strategies;
mod trading;
mod utils;

use paste;

use std::slice;
use backtest::{backtest, BacktestResult};
// See TODO in macro_rules for aliasing.
use indicators::{Ema as ema, Ema2 as ema2, Sma as sma, Smma as smma};
use strategies::{MAMACX, Strategy};
pub use common::{Advice, Candle, Fees, Trend};
pub use filters::Filters;
pub use trading::{Position, TradingContext, TradingSummary};

macro_rules! mamacx {
    ($short_ma:ident $long_ma:ident) => {
        paste::item! {
            #[no_mangle]
            // TODO: No elegant way to lowercase idents.
            pub unsafe extern "C" fn [<$short_ma $long_ma cx>](
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
                        $short_ma::new(short_period),
                        $long_ma::new(long_period),
                        neg_threshold,
                        pos_threshold,
                        persistence,
                    )
                };
                run_test(
                    strategy_factory,
                    candles,
                    length,
                    fees,
                    filters,
                    interval,
                    quote,
                    missed_candle_policy,
                    trailing_stop,
                )
            }
        }
    }
}

mamacx!(ema ema);
mamacx!(ema ema2);
mamacx!(ema sma);
mamacx!(ema smma);
mamacx!(ema2 ema);
mamacx!(ema2 ema2);
mamacx!(ema2 sma);
mamacx!(ema2 smma);
mamacx!(sma ema);
mamacx!(sma ema2);
mamacx!(sma sma);
mamacx!(sma smma);
mamacx!(smma ema);
mamacx!(smma ema2);
mamacx!(smma sma);
mamacx!(smma smma);

unsafe fn run_test<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: *const Candle,
    length: u32,
    fees: *const Fees,
    filters: *const Filters,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    trailing_stop: f64,
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

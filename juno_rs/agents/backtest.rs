use crate::{/*Advice,*/ Candle, Fees};
use crate::filters::Filters;
use crate::strategies::Strategy;

pub type BacktestResult = (f64, f64, f64, f64, u64);

pub fn backtest<T: Strategy>(
    mut strategy: T,
    // candles: Vec<Candle>,
    // fees: Fees,
    // filters: Filters,
    quote: f64,
) -> BacktestResult {
    (0.0, 0.0, 0.0, 0.0, 0)
}

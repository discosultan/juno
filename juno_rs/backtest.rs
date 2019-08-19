use crate::{/*Advice,*/ Candle, Fees, Filters, TradingSummary, Position};
use crate::strategies::Strategy;

pub type BacktestResult = (f64, f64, f64, f64, u64);

pub fn backtest<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    quote: f64,
) -> BacktestResult {
    let mut result = TradingSummary::new(quote, fees, filters);
    let mut open_position: Option<Position> = None;

    loop {
        let mut last_candle: Option<Candle> = None;
        let mut restart = false;

        let mut strategy = strategy_factory();

        for candle in candles {
            
        }
    }

    (0.0, 0.0, 0.0, 0.0, 1)
}

use crate::{Advice, Candle, Fees, Filters, TradingSummary, Position};
use crate::strategies::Strategy;

pub type BacktestResult = (f64, f64, f64, f64, u64);

pub fn backtest<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    interval: u64,
    quote: f64,
) -> BacktestResult {
    let restart_on_missed_candle = false;

    let mut result = TradingSummary::new(quote, fees, filters);
    let mut open_position: Option<Position> = None;

    loop {
        let mut last_candle: Option<&Candle> = None;
        let mut restart = false;

        let mut strategy = strategy_factory();

        for candle in candles {
            result.append_candle(candle);

            // TODO: match
            if last_candle.is_some() && candle.time - last_candle.unwrap().time >= interval * 2 {
                if restart_on_missed_candle {
                    restart = true;
                    break;
                }
            }

            last_candle = Some(candle);
            let advice = strategy.update(candle);

            if open_position.is_none() && advice == Advice::Buy {
                // if !try_open_position
            } else if open_position.is_some() && advice == Advice::Sell {
                // close
            }
        }

        if !restart {
            break;
        }
    }

    (
        result.profit(),
        result.mean_drawdown(),
        result.max_drawdown(),
        result.mean_position_profit(),
        result.mean_position_duration(),
    )
}

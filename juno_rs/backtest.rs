use crate::strategies::Strategy;
use crate::{Advice, Candle, Fees, Filters, Position, TradingContext, TradingSummary};

pub type BacktestResult = (f64, f64, f64, f64, u64);

pub fn backtest<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    interval: u64,
    start: u64,
    end: u64,
    quote: f64,
) -> BacktestResult {
    let restart_on_missed_candle = false;

    let mut result = TradingSummary::new(start, end, quote, fees, filters);
    let mut ctx = TradingContext::new(quote);
    let mut last_candle: Option<&Candle>;

    loop {
        let mut restart = false;
        last_candle = None;

        let mut strategy = strategy_factory();

        for candle in candles {
            result.append_candle(candle);

            if let Some(last_candle) = last_candle {
                if restart_on_missed_candle && candle.time - last_candle.time >= interval * 2 {
                    restart = true;
                    break;
                }
            }

            last_candle = Some(candle);
            let advice = strategy.update(candle);

            if ctx.open_position.is_none() && advice == Advice::Buy {
                if !try_open_position(&mut ctx, fees, filters, candle) {
                    break;
                }
            } else if ctx.open_position.is_some() && advice == Advice::Sell {
                close_position(&mut ctx, &mut result, fees, filters, candle);
            }
        }

        if !restart {
            break;
        }
    }

    if let Some(last_candle) = last_candle {
        if ctx.open_position.is_some() {
            close_position(&mut ctx, &mut result, fees, filters, last_candle);
        }
    }

    result.calculate();
    (
        result.profit,
        result.mean_drawdown,
        result.max_drawdown,
        result.mean_position_profit,
        result.mean_position_duration,
    )
}

fn try_open_position(
    ctx: &mut TradingContext,
    fees: &Fees,
    filters: &Filters,
    candle: &Candle,
) -> bool {
    let price = candle.close;
    let size = filters.size.round_down(ctx.quote / price);
    if size == 0.0 {
        return false;
    }

    let fee = size * fees.taker;
    ctx.open_position = Some(Position::new(candle.time, price, size, fee));

    ctx.quote -= price * size;

    true
}

fn close_position(
    ctx: &mut TradingContext,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    candle: &Candle,
) {
    let price = candle.close;
    if let Some(mut pos) = ctx.open_position.take() {
        let size = filters.size.round_down(pos.size - pos.fee);

        let quote = size * price;
        let fee = quote * fees.taker;

        pos.close(candle.time, price, size, fee);
        summary.append_position(pos);

        ctx.open_position = None;
        ctx.quote = quote - fee;
    } else {
        panic!();
    }
}

use crate::strategies::Strategy;
use crate::{Advice, Candle, Fees, Filters, Position, TradingContext, TradingSummary};
use crate::math::round_half_up;

pub type BacktestResult = (f64, f64, f64, f64, u64, u32, u32);

pub fn backtest<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    interval: u64,
    start: u64,
    end: u64,
    quote: f64,
    restart_on_missed_candle: bool,
    trailing_stop: f64,
) -> BacktestResult {
    let mut summary = TradingSummary::new(start, end, quote, fees, filters);
    let mut ctx = TradingContext::new(quote);
    let mut last_candle: Option<&Candle> = None;
    let mut strategy = strategy_factory();
    let mut highest_close_since_position = 0.0;
    let mut i = 0;
    loop {
        let mut restart = false;

        for candle in candles[i..candles.len()].iter() {
            i += 1;
            summary.append_candle(candle);

            if let Some(last_candle) = last_candle {
                if restart_on_missed_candle && candle.time - last_candle.time >= interval * 2 {
                    restart = true;
                    strategy = strategy_factory();
                }
            }

            let advice = strategy.update(candle);

            if ctx.open_position.is_none() && advice == Advice::Buy {
                if !try_open_position(&mut ctx, fees, filters, candle) {
                    break;
                }
                highest_close_since_position = candle.close
            } else if ctx.open_position.is_some() && advice == Advice::Sell {
                close_position(&mut ctx, &mut summary, fees, filters, candle);
            } else if trailing_stop != 0.0 && ctx.open_position.is_some() {
                highest_close_since_position = f64::max(
                    highest_close_since_position, candle.close);
                let trailing_factor = 1.0 - trailing_stop;
                if candle.close <= highest_close_since_position * trailing_factor {
                    close_position(&mut ctx, &mut summary, fees, filters, candle);
                }
            }

            last_candle = Some(candle);

            if restart {
                break;
            }
        }

        if !restart {
            break;
        }
    }

    if let Some(last_candle) = last_candle {
        if ctx.open_position.is_some() {
            close_position(&mut ctx, &mut summary, fees, filters, last_candle);
        }
    }

    summary.calculate();
    (
        summary.profit,
        summary.mean_drawdown,
        summary.max_drawdown,
        summary.mean_position_profit,
        summary.mean_position_duration,
        summary.num_positions_in_profit,
        summary.num_positions_in_loss,
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

    let fee = round_half_up(size * fees.taker, filters.base_precision);
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
        let fee = round_half_up(quote * fees.taker, filters.quote_precision);

        pos.close(candle.time, price, size, fee);
        summary.append_position(pos);

        ctx.open_position = None;
        ctx.quote += quote - fee;
    } else {
        panic!();
    }
}

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
    missed_candle_policy: u32,
    trailing_stop: f64,
) -> BacktestResult {
    let two_interval = interval * 2;
    let mut summary = TradingSummary::new(start, end, quote, fees, filters);
    let mut ctx = TradingContext::new(strategy_factory(), quote);
    let mut i = 0;
    loop {
        let mut restart = false;
        let mut exit = false;

        for candle in candles[i..candles.len()].iter() {
            i += 1;
            summary.append_candle(candle);

            if let Some(last_candle) = ctx.last_candle {
                let diff = candle.time - last_candle.time;
                if missed_candle_policy == 1 && diff >= two_interval {
                    restart = true;
                    ctx.strategy = strategy_factory();
                } else if missed_candle_policy == 2 && diff >= two_interval {
                    let num_missed = (diff / interval) - 1;
                    for _ in 0..num_missed {
                        if !tick(&mut ctx, &mut summary, &fees, &filters, trailing_stop, candle) {
                            exit = true;
                            break;
                        }
                    }
                }
            }

            if exit {
                break;
            }

            if !tick(&mut ctx, &mut summary, &fees, &filters, trailing_stop, candle) {
                exit = true;
                break;
            }

            if restart {
                break;
            }
        }

        if exit || !restart {
            break;
        }
    }

    if let Some(last_candle) = ctx.last_candle {
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

fn tick<'a, T: Strategy>(
    mut ctx: &mut TradingContext<'a, T>,
    mut summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    trailing_stop: f64,
    candle: &'a Candle,
) -> bool {
    let advice = ctx.strategy.update(&candle);

    if ctx.open_position.is_none() && advice == Advice::Buy {
        if !try_open_position(&mut ctx, fees, filters, &candle) {
            return false;
        }
        ctx.highest_close_since_position = candle.close
    } else if ctx.open_position.is_some() && advice == Advice::Sell {
        close_position(&mut ctx, &mut summary, fees, filters, &candle);
    } else if trailing_stop != 0.0 && ctx.open_position.is_some() {
        ctx.highest_close_since_position = f64::max(
            ctx.highest_close_since_position, candle.close);
        let trailing_factor = 1.0 - trailing_stop;
        if candle.close <= ctx.highest_close_since_position * trailing_factor {
            close_position(&mut ctx, &mut summary, fees, filters, &candle);
        }
    }

    ctx.last_candle = Some(candle);
    true
}

fn try_open_position<T: Strategy>(
    ctx: &mut TradingContext<T>,
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

fn close_position<T: Strategy>(
    ctx: &mut TradingContext<T>,
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

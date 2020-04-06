use crate::math::round_half_up;
use crate::strategies::Strategy;
use crate::{Advice, Candle, Fees, Filters, Position, TradingSummary};

struct Context<T: Strategy> {
    pub strategy: T,
    pub quote: f64,
    pub open_position: Option<Position>,
    pub last_candle: Option<Candle>,
    pub highest_close_since_position: f64,
}

impl<T: Strategy> Context<T> {
    pub fn new(strategy: T, quote: f64) -> Self {
        Self {
            strategy,
            quote,
            open_position: None,
            last_candle: None,
            highest_close_since_position: 0.0,
        }
    }
}

pub fn trade<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    trailing_stop: f64,
) -> TradingSummary {
    let two_interval = interval * 2;

    let candles_len = candles.len();
    let (start, end) = if candles_len == 0 {
        (0, interval)
    } else {
        (candles[0].time, candles[candles_len - 1].time + interval)
    };

    let mut summary = TradingSummary::new(interval, start, end, quote);
    let mut ctx = Context::new(strategy_factory(), quote);
    let mut i = 0;
    loop {
        let mut restart = false;
        let mut exit = false;

        for candle in candles[i..candles.len()].iter() {
            i += 1;

            if let Some(last_candle) = ctx.last_candle {
                let diff = candle.time - last_candle.time;
                if missed_candle_policy == 1 && diff >= two_interval {
                    restart = true;
                    ctx.strategy = strategy_factory();
                } else if missed_candle_policy == 2 && diff >= two_interval {
                    let num_missed = diff / interval - 1;
                    for i in 1..=num_missed {
                        let missed_candle = Candle {
                            time: last_candle.time + i * interval,
                            open: last_candle.open,
                            high: last_candle.high,
                            low: last_candle.low,
                            close: last_candle.close,
                            volume: last_candle.volume,
                        };
                        if !tick(
                            &mut ctx,
                            &mut summary,
                            &fees,
                            &filters,
                            trailing_stop,
                            &missed_candle,
                        ) {
                            exit = true;
                            break;
                        }
                    }
                }
            }

            if exit {
                break;
            }

            if !tick(
                &mut ctx,
                &mut summary,
                &fees,
                &filters,
                trailing_stop,
                candle,
            ) {
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
            close_position(&mut ctx, &mut summary, fees, filters, &last_candle);
        }
    }

    summary.calculate();
    summary
}

fn tick<T: Strategy>(
    mut ctx: &mut Context<T>,
    mut summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    trailing_stop: f64,
    candle: &Candle,
) -> bool {
    let advice = ctx.strategy.update(&candle);

    if ctx.open_position.is_none() && advice == Some(Advice::Buy) {
        if !try_open_position(&mut ctx, fees, filters, &candle) {
            return false;
        }
        ctx.highest_close_since_position = candle.close
    } else if ctx.open_position.is_some() && advice == Some(Advice::Sell) {
        close_position(&mut ctx, &mut summary, fees, filters, &candle);
    } else if trailing_stop != 0.0 && ctx.open_position.is_some() {
        ctx.highest_close_since_position = f64::max(ctx.highest_close_since_position, candle.close);
        let trailing_factor = 1.0 - trailing_stop;
        if candle.close <= ctx.highest_close_since_position * trailing_factor {
            close_position(&mut ctx, &mut summary, fees, filters, &candle);
        }
    }

    ctx.last_candle = Some(*candle);
    true
}

fn try_open_position<T: Strategy>(
    ctx: &mut Context<T>,
    fees: &Fees,
    filters: &Filters,
    candle: &Candle,
) -> bool {
    let price = candle.close;
    let size = filters.size.round_down(ctx.quote / price);
    if size == 0.0 {
        return false;
    }

    let quote = round_half_up(price * size, filters.quote_precision);
    let fee = round_half_up(size * fees.taker, filters.base_precision);

    ctx.open_position = Some(Position::new(candle.time, price, size, quote, fee));
    ctx.quote -= quote;

    true
}

fn close_position<T: Strategy>(
    ctx: &mut Context<T>,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    candle: &Candle,
) {
    let price = candle.close;
    if let Some(mut pos) = ctx.open_position.take() {
        let size = filters.size.round_down(pos.base_gain);

        let quote = round_half_up(price * size, filters.quote_precision);
        let fee = round_half_up(quote * fees.taker, filters.quote_precision);

        pos.close(candle.time, price, size, quote, fee);
        summary.append_position(pos);

        ctx.open_position = None;
        ctx.quote += quote - fee;
    } else {
        panic!();
    }
}

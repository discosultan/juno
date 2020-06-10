use crate::{
    math::{ceil_multiple, round_down, round_half_up},
    strategies::{Changed, Strategy},
    trading::{StopLoss, TakeProfit},
    Advice, BorrowInfo, Candle, Fees, Filters, LongPosition, ShortPosition, TradingSummary,
};

const HOUR_MS: u64 = 3_600_000;

struct State<T: Strategy> {
    pub strategy: T,
    pub changed: Changed,
    pub quote: f64,
    pub open_long_position: Option<LongPosition>,
    pub open_short_position: Option<ShortPosition>,
    pub last_candle: Option<Candle>,
    pub stop_loss: StopLoss,
    pub take_profit: TakeProfit,
}

impl<T: Strategy> State<T> {
    pub fn new(strategy: T, quote: f64, stop_loss: f64, take_profit: f64) -> Self {
        Self {
            strategy,
            changed: Changed::new(true),
            quote,
            open_long_position: None,
            open_short_position: None,
            last_candle: None,
            stop_loss: StopLoss::new(stop_loss, true),
            take_profit: TakeProfit::new(take_profit),
        }
    }
}

pub fn trade<TF: Fn() -> TS, TS: Strategy>(
    strategy_factory: TF,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    margin_multiplier: u32,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    stop_loss: f64,
    take_profit: f64,
    long: bool,
    short: bool,
) -> TradingSummary {
    let two_interval = interval * 2;

    let candles_len = candles.len();
    let (start, end) = if candles_len == 0 {
        (0, interval)
    } else {
        (candles[0].time, candles[candles_len - 1].time + interval)
    };

    let mut summary = TradingSummary::new(interval, start, end, quote);
    let mut state = State::new(strategy_factory(), quote, stop_loss, take_profit);
    let mut i = 0;
    loop {
        let mut restart = false;
        let mut exit = false;

        for candle in candles[i..candles.len()].iter() {
            i += 1;

            if let Some(last_candle) = state.last_candle {
                let diff = candle.time - last_candle.time;
                if missed_candle_policy == 1 && diff >= two_interval {
                    restart = true;
                    state.strategy = strategy_factory();
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
                            &mut state,
                            &mut summary,
                            &fees,
                            &filters,
                            &borrow_info,
                            margin_multiplier,
                            interval,
                            long,
                            short,
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
                &mut state,
                &mut summary,
                &fees,
                &filters,
                &borrow_info,
                margin_multiplier,
                interval,
                long,
                short,
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

    if let Some(last_candle) = state.last_candle {
        if state.open_long_position.is_some() {
            close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                last_candle.time + interval,
                last_candle.close,
            );
        }
        if state.open_short_position.is_some() {
            close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                last_candle.time + interval,
                last_candle.close,
            );
        }
    }

    summary.calculate();
    summary
}

fn tick<T: Strategy>(
    mut state: &mut State<T>,
    mut summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    margin_multiplier: u32,
    interval: u64,
    long: bool,
    short: bool,
    candle: &Candle,
) -> bool {
    state.stop_loss.update(candle);
    state.take_profit.update(candle);
    let advice = state.changed.update(state.strategy.update(&candle));

    if state.open_long_position.is_some() {
        if advice == Advice::Short || advice == Advice::Liquidate {
            close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                candle.time + interval,
                candle.close,
            );
        } else if state.stop_loss.upside_hit() || state.take_profit.upside_hit() {
            close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                candle.time + interval,
                candle.close,
            );
        }
    } else if state.open_short_position.is_some() {
        if advice == Advice::Long || advice == Advice::Liquidate {
            close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                candle.time + interval,
                candle.close,
            );
        } else if state.stop_loss.downside_hit() || state.take_profit.downside_hit() {
            close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                candle.time + interval,
                candle.close,
            );
        }
    }

    if state.open_long_position.is_none() && state.open_short_position.is_none() {
        if long && advice == Advice::Long {
            if !try_open_long_position(
                &mut state,
                fees,
                filters,
                candle.time + interval,
                candle.close,
            ) {
                return false;
            }
        } else if short && advice == Advice::Short {
            if !try_open_short_position(
                &mut state,
                fees,
                filters,
                margin_multiplier,
                candle.time + interval,
                candle.close,
            ) {
                return false;
            }
        }
        state.stop_loss.clear(candle);
        state.take_profit.clear(candle);
    }

    state.last_candle = Some(*candle);
    true
}

fn try_open_long_position<T: Strategy>(
    state: &mut State<T>,
    fees: &Fees,
    filters: &Filters,
    time: u64,
    price: f64,
) -> bool {
    let size = filters.size.round_down(state.quote / price);
    if size == 0.0 {
        return false;
    }

    let quote = round_down(price * size, filters.quote_precision);
    let fee = round_half_up(size * fees.taker, filters.base_precision);

    state.open_long_position = Some(LongPosition::new(time, price, size, quote, fee));
    state.quote -= quote;

    true
}

fn close_long_position<T: Strategy>(
    state: &mut State<T>,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    time: u64,
    price: f64,
) {
    if let Some(mut pos) = state.open_long_position.take() {
        let size = filters.size.round_down(pos.base_gain);

        let quote = round_down(price * size, filters.quote_precision);
        let fee = round_half_up(quote * fees.taker, filters.quote_precision);

        pos.close(time, price, size, quote, fee);
        summary.append_long_position(pos);

        state.open_long_position = None;
        state.quote += quote - fee;
    } else {
        panic!();
    }
}

fn try_open_short_position<T: Strategy>(
    state: &mut State<T>,
    fees: &Fees,
    filters: &Filters,
    margin_multiplier: u32,
    time: u64,
    price: f64,
) -> bool {
    let collateral_size = filters.size.round_down(state.quote / price);
    if collateral_size == 0.0 {
        return false;
    }
    let borrowed = collateral_size * (margin_multiplier - 1) as f64;

    let quote = round_down(price * borrowed, filters.quote_precision);
    let fee = round_half_up(quote * fees.taker, filters.quote_precision);

    state.open_short_position = Some(ShortPosition::new(
        time,
        state.quote,
        borrowed,
        price,
        borrowed,
        quote,
        fee,
    ));

    state.quote += quote - fee;
    true
}

fn close_short_position<T: Strategy>(
    state: &mut State<T>,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    time: u64,
    price: f64,
) {
    if let Some(mut pos) = state.open_short_position.take() {
        let borrowed = pos.borrowed;

        let duration = ceil_multiple(time - pos.time, HOUR_MS) / HOUR_MS;
        let hourly_interest_rate = borrow_info.daily_interest_rate / 24.0;
        let interest = borrowed * duration as f64 * hourly_interest_rate;

        let mut size = borrowed + interest;
        let quote = round_down(price * size, filters.quote_precision);
        let fee = round_half_up(size * fees.taker, filters.base_precision);
        size += fee;

        pos.close(interest, time, price, size, quote, fee);
        summary.append_short_position(pos);

        state.open_short_position = None;
        state.quote -= quote;
    } else {
        panic!();
    }
}

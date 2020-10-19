use crate::{
    math::{ceil_multiple, round_down, round_half_up},
    strategies::Changed,
    strategies::Signal,
    time,
    trading::{LongPosition, Position, ShortPosition, StopLoss, TakeProfit, TradingSummary},
    Advice, BorrowInfo, Candle, Fees, Filters,
};

struct State<T: Signal> {
    pub strategy: T,
    pub changed: Changed,
    pub quote: f64,
    pub open_position: Option<Position>,
    pub last_candle: Option<Candle>,
    pub stop_loss: StopLoss,
    pub take_profit: TakeProfit,
}

impl<T: Signal> State<T> {
    pub fn new(
        strategy: T,
        quote: f64,
        stop_loss: f64,
        trail_stop_loss: bool,
        take_profit: f64,
    ) -> Self {
        Self {
            strategy,
            changed: Changed::new(true),
            quote,
            open_position: None,
            last_candle: None,
            stop_loss: StopLoss::new(stop_loss, trail_stop_loss),
            take_profit: TakeProfit::new(take_profit),
        }
    }
}

pub fn trade<T: Signal>(
    strategy_params: &T::Params,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    margin_multiplier: u32,
    interval: u64,
    quote: f64,
    missed_candle_policy: u32,
    stop_loss: f64,
    trail_stop_loss: bool,
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

    let mut summary = TradingSummary::new(start, end, quote);
    let mut state = State::new(
        T::new(strategy_params),
        quote,
        stop_loss,
        trail_stop_loss,
        take_profit,
    );
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
                    state.strategy = T::new(strategy_params);
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
                        if tick(
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
                        )
                        .is_err()
                        {
                            exit = true;
                            break;
                        }
                    }
                }
            }

            if exit {
                break;
            }

            if tick(
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
            )
            .is_err()
            {
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
        match state.open_position {
            Some(Position::Long(_)) => close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                last_candle.time + interval,
                last_candle.close,
            ),
            Some(Position::Short(_)) => close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                last_candle.time + interval,
                last_candle.close,
            ),
            None => {}
        }
    }

    summary
}

fn tick<T: Signal>(
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
) -> Result<(), &'static str> {
    state.stop_loss.update(candle);
    state.take_profit.update(candle);
    state.strategy.update(&candle);
    let advice = state.changed.update(state.strategy.advice());

    match state.open_position {
        Some(Position::Long(_))
            if advice == Advice::Short
                || advice == Advice::Liquidate
                || state.stop_loss.upside_hit()
                || state.take_profit.upside_hit() =>
        {
            close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                candle.time + interval,
                candle.close,
            )
        }
        Some(Position::Short(_))
            if advice == Advice::Long
                || advice == Advice::Liquidate
                || state.stop_loss.downside_hit()
                || state.take_profit.downside_hit() =>
        {
            close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                candle.time + interval,
                candle.close,
            )
        }
        _ => {}
    }

    if state.open_position.is_none() {
        if long && advice == Advice::Long {
            try_open_long_position(
                &mut state,
                fees,
                filters,
                candle.time + interval,
                candle.close,
            )?;
        } else if short && advice == Advice::Short {
            try_open_short_position(
                &mut state,
                fees,
                filters,
                borrow_info,
                margin_multiplier,
                candle.time + interval,
                candle.close,
            )?;
        }
        state.stop_loss.clear(candle);
        state.take_profit.clear(candle);
    }

    state.last_candle = Some(*candle);
    Ok(())
}

fn try_open_long_position<T: Signal>(
    state: &mut State<T>,
    fees: &Fees,
    filters: &Filters,
    time: u64,
    price: f64,
) -> Result<(), &'static str> {
    let size = filters.size.round_down(state.quote / price);
    if size == 0.0 {
        return Err("size 0");
    }

    let quote = round_down(price * size, filters.quote_precision);
    let fee = round_half_up(size * fees.taker, filters.base_precision);

    state.open_position = Some(Position::Long(LongPosition::new(
        time, price, size, quote, fee,
    )));
    state.quote -= quote;

    Ok(())
}

fn close_long_position<T: Signal>(
    state: &mut State<T>,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    time: u64,
    price: f64,
) {
    if let Some(Position::Long(mut pos)) = state.open_position.take() {
        let size = filters.size.round_down(pos.base_gain);

        let quote = round_down(price * size, filters.quote_precision);
        let fee = round_half_up(quote * fees.taker, filters.quote_precision);

        pos.close(time, price, size, quote, fee);
        summary.positions.push(Position::Long(pos));

        state.open_position = None;
        state.quote += quote - fee;
    } else {
        // TODO: Refactor to get rid of this.
        panic!();
    }
}

fn try_open_short_position<T: Signal>(
    state: &mut State<T>,
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    margin_multiplier: u32,
    time: u64,
    price: f64,
) -> Result<(), &'static str> {
    let collateral_size = filters.size.round_down(state.quote / price);
    if collateral_size == 0.0 {
        return Err("collateral 0");
    }
    let borrowed = f64::min(
        collateral_size * (margin_multiplier - 1) as f64,
        borrow_info.limit,
    );

    let quote = round_down(price * borrowed, filters.quote_precision);
    let fee = round_half_up(quote * fees.taker, filters.quote_precision);

    state.open_position = Some(Position::Short(ShortPosition::new(
        time,
        state.quote,
        borrowed,
        price,
        borrowed,
        quote,
        fee,
    )));

    state.quote += quote - fee;
    Ok(())
}

fn close_short_position<T: Signal>(
    state: &mut State<T>,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    time: u64,
    price: f64,
) {
    if let Some(Position::Short(mut pos)) = state.open_position.take() {
        let borrowed = pos.borrowed;

        let duration = ceil_multiple(time - pos.time, time::HOUR_MS) / time::HOUR_MS;
        let hourly_interest_rate = borrow_info.daily_interest_rate / 24.0;
        let interest = borrowed * duration as f64 * hourly_interest_rate;

        let mut size = borrowed + interest;
        let quote = round_down(price * size, filters.quote_precision);
        let fee = round_half_up(size * fees.taker, filters.base_precision);
        size += fee;

        pos.close(interest, time, price, size, quote, fee);
        summary.positions.push(Position::Short(pos));

        state.open_position = None;
        state.quote -= quote;
    } else {
        panic!();
    }
}

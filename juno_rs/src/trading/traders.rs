use crate::{
    math::{ceil_multiple, round_down, round_half_up},
    stop_loss::{StopLoss, StopLossParams},
    strategies::{Signal, StrategyMeta, StrategyParams},
    take_profit::{TakeProfit, TakeProfitParams},
    time,
    trading::{
        CloseReason, OpenLongPosition, OpenPosition, OpenShortPosition, Position, TradingSummary,
    },
    utils::Changed,
    Advice, BorrowInfo, Candle, Fees, Fill, Filters,
};

use super::MissedCandlePolicy;

struct State {
    pub strategy: Box<dyn Signal>,
    pub stop_loss: Box<dyn StopLoss>,
    pub take_profit: Box<dyn TakeProfit>,
    pub changed: Changed,
    pub quote: f64,
    pub open_position: Option<OpenPosition>,
    pub last_candle: Option<Candle>,
}

impl State {
    pub fn new(
        quote: f64,
        strategy: Box<dyn Signal>,
        stop_loss: Box<dyn StopLoss>,
        take_profit: Box<dyn TakeProfit>,
    ) -> Self {
        Self {
            strategy,
            stop_loss,
            take_profit,
            quote,
            changed: Changed::new(true),
            open_position: None,
            last_candle: None,
        }
    }
}

pub fn trade(
    strategy_params: &StrategyParams,
    stop_loss_params: &StopLossParams,
    take_profit_params: &TakeProfitParams,
    candles: &[Candle],
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    margin_multiplier: u32,
    interval: u64,
    quote: f64,
    missed_candle_policy: MissedCandlePolicy,
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

    let strategy_meta = StrategyMeta { interval };

    let mut summary = TradingSummary::new(start, end, quote);
    let mut state = State::new(
        quote,
        strategy_params.construct(&strategy_meta),
        stop_loss_params.construct(),
        take_profit_params.construct(),
    );

    for candle in candles {
        let mut exit = false;

        if let Some(last_candle) = state.last_candle {
            let diff = candle.time - last_candle.time;
            if missed_candle_policy == MissedCandlePolicy::Restart && diff >= two_interval {
                state.strategy = strategy_params.construct(&strategy_meta);
            } else if missed_candle_policy == MissedCandlePolicy::Last && diff >= two_interval {
                let num_missed = diff / interval - 1;
                for i in 1..=num_missed {
                    let missed_candle = Candle {
                        time: last_candle.time + i * interval,
                        open: last_candle.close,
                        high: last_candle.close,
                        low: last_candle.close,
                        close: last_candle.close,
                        volume: 0.0,
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
            break;
        }
    }

    if let Some(last_candle) = state.last_candle {
        match state.open_position {
            Some(OpenPosition::Long(_)) => close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                last_candle.time + interval,
                last_candle.close,
                CloseReason::Cancelled,
            ),
            Some(OpenPosition::Short(_)) => close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                last_candle.time + interval,
                last_candle.close,
                CloseReason::Cancelled,
            ),
            None => {}
        }
    }

    summary
}

fn tick(
    mut state: &mut State,
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

    if let Some(OpenPosition::Long(_)) = state.open_position {
        if advice == Advice::Short || advice == Advice::Liquidate {
            close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                candle.time + interval,
                candle.close,
                CloseReason::Strategy,
            )
        } else if state.stop_loss.upside_hit() {
            close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                candle.time + interval,
                candle.close,
                CloseReason::StopLoss,
            )
        } else if state.take_profit.upside_hit() {
            close_long_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                candle.time + interval,
                candle.close,
                CloseReason::TakeProfit,
            )
        }
    } else if let Some(OpenPosition::Short(_)) = state.open_position {
        if advice == Advice::Long || advice == Advice::Liquidate {
            close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                candle.time + interval,
                candle.close,
                CloseReason::Strategy,
            )
        } else if state.stop_loss.downside_hit() {
            close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                candle.time + interval,
                candle.close,
                CloseReason::StopLoss,
            )
        } else if state.take_profit.downside_hit() {
            close_short_position(
                &mut state,
                &mut summary,
                fees,
                filters,
                borrow_info,
                candle.time + interval,
                candle.close,
                CloseReason::TakeProfit,
            )
        }
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

fn try_open_long_position(
    state: &mut State,
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

    state.open_position = Some(OpenPosition::Long(OpenLongPosition {
        time,
        fills: [Fill {
            price,
            size,
            quote,
            fee,
        }],
    }));
    state.quote -= quote;

    Ok(())
}

fn close_long_position(
    state: &mut State,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    time: u64,
    price: f64,
    reason: CloseReason,
) {
    if let Some(OpenPosition::Long(pos)) = state.open_position.take() {
        let size = filters.size.round_down(pos.base_gain());

        let quote = round_down(price * size, filters.quote_precision);
        let fee = round_half_up(quote * fees.taker, filters.quote_precision);

        let pos = pos.close(
            time,
            [Fill {
                price,
                size,
                quote,
                fee,
            }],
            reason,
        );
        summary.positions.push(Position::Long(pos));

        state.open_position = None;
        state.quote += quote - fee;
    } else {
        // TODO: Refactor to get rid of this.
        panic!();
    }
}

fn try_open_short_position(
    state: &mut State,
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

    state.open_position = Some(OpenPosition::Short(OpenShortPosition {
        time,
        collateral: state.quote,
        borrowed,
        fills: [Fill {
            price,
            size: borrowed,
            quote,
            fee,
        }],
    }));

    state.quote += quote - fee;
    Ok(())
}

fn close_short_position(
    state: &mut State,
    summary: &mut TradingSummary,
    fees: &Fees,
    filters: &Filters,
    borrow_info: &BorrowInfo,
    time: u64,
    price: f64,
    reason: CloseReason,
) {
    if let Some(OpenPosition::Short(pos)) = state.open_position.take() {
        let borrowed = pos.borrowed;

        let duration = ceil_multiple(time - pos.time, time::HOUR_MS) / time::HOUR_MS;
        let hourly_interest_rate = borrow_info.daily_interest_rate / 24.0;
        let interest = borrowed * duration as f64 * hourly_interest_rate;

        let mut size = borrowed + interest;
        let fee = round_half_up(size * fees.taker, filters.base_precision);
        size += fee;
        let quote = round_down(price * size, filters.quote_precision);

        let pos = pos.close(
            time,
            [Fill {
                price,
                size,
                fee,
                quote,
            }],
            reason,
        );
        summary.positions.push(Position::Short(pos));

        state.open_position = None;
        state.quote -= quote;
    } else {
        panic!();
    }
}

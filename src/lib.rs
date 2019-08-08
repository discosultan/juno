use pyo3::prelude::*;
use pyo3::wrap_pyfunction;

mod filters;
mod indicators;
mod strategies;
mod utils;

use filters::Filters;

pub type BacktestResult = (f64, f64, f64, f64, u64);

pub fn emaemacx(
    candles: Vec<Candle>,
    fees: Fees,
    filters: Filters,
    short_period: u32,
    long_period: u32,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: u32,
) -> BacktestResult {
    let mut strategy = EmaEmaCx::new(short_period, long_period, neg_threshold, pos_threshold, persistence);

}

pub struct Candle {
    time: u64,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    closed: bool,
}

pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

impl Fees {
    pub fn none() -> Self {
        Fees {
            maker: 0.0,
            taker: 0.0,
        }
    }
}

use std::slice;
use strategies::Strategy;
use utils::*;

pub unsafe fn backtest<T: Strategy>(
    strategy: &mut T,
    acc_info: *const AccountInfo,
    ap_info: *const AssetPairInfo,
    interval: u64,
    candles: *const Candle,
    length: u32,
) -> BacktestResult {
    // Turn unsafe ptrs to safe references.
    let acc_info = &*acc_info;
    let ap_info = &*ap_info;
    let candles = slice::from_raw_parts(candles, length as usize);

    let mut ctx = TradingContext::new(interval, ap_info, acc_info);
pub unsafe fn backtest<T: Strategy>(
    strategy: &mut T,
    acc_info: *const AccountInfo,
    ap_info: *const AssetPairInfo,
    interval: u64,
    candles: *const Candle,
    length: u32,
) -> BacktestResult {
    // Turn unsafe ptrs to safe references.
    let acc_info = &*acc_info;
    let ap_info = &*ap_info;
    let candles = slice::from_raw_parts(candles, length as usize);

    let mut curr_advice = Some(Advice::Short);

    for candle in candles {
        let mut base_delta = 0.0;
        let mut quote_delta = 0.0;
        let advice = strategy.update(candle);
        if advice != None && advice != curr_advice {
            curr_advice = advice;
            if advice == Some(Advice::Long) {
                let qty = adjust_qty(ctx.quote_balance / candle.close, ap_info);
                if qty >= ap_info.min_qty {
                    base_delta = qty - qty * acc_info.taker_fee;
                    quote_delta = -qty * candle.close;
                }
            } else if advice == Some(Advice::Short) {
                let qty = adjust_qty(ctx.base_balance, ap_info);
                if qty >= ap_info.min_qty {
                    base_delta = -qty;
                    quote_delta = qty * candle.close;
                    quote_delta -= quote_delta * acc_info.taker_fee;
                }
            }
        }
        ctx.update(candle, base_delta, quote_delta);
    }

    if let Some(candle) = ctx.last_candle {
        if curr_advice == Some(Advice::Long) {
            let qty = adjust_qty(ctx.base_balance, ap_info);
            if qty >= ap_info.min_qty {
                let base_delta = -qty;
                let mut quote_delta = qty * candle.close;
                quote_delta -= quote_delta * acc_info.taker_fee;
                ctx.update(candle, base_delta, quote_delta);
            }
        }
    }

    let drawdowns = ctx.drawdowns();
    (
        ctx.total_profit(),
        ctx.mean_drawdown(&drawdowns),
        ctx.max_drawdown(&drawdowns),
        ctx.mean_position_profit(),
        ctx.mean_position_duration(),
    )
}

fn adjust_qty(qty: f64, ap_info: &AssetPairInfo) -> f64 {
    let qty = qty.min(ap_info.max_qty);
    let qty = (qty / ap_info.qty_step_size).round() * ap_info.qty_step_size;
    let factor = f64::from(10_i32.pow(ap_info.base_precision));
    (qty * factor).round() / factor
}

use std::slice;
use strategies::Strategy;
use utils::*;

pub unsafe fn backtest<T: Strategy>(
    candles: Vec<Candle>,
    fees: Fees,
    filters: Filters,
    interval: u64,
    quote: f64,
) -> BacktestResult {
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

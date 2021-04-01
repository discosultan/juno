use criterion::{criterion_group, criterion_main, Criterion};
use juno_rs::{
    filters::{Filters, Price, Size},
    stop_loss::{self, StopLossParams},
    strategies::{FourWeekRuleParams, StrategyParams},
    take_profit::{self, TakeProfitParams},
    time,
    trading::{self, MissedCandlePolicy, TraderParams, TradingParams},
    BorrowInfo, Candle, Fees,
};
use std::collections::HashMap;

fn trade_benchmark(c: &mut Criterion) {
    let strategy = StrategyParams::FourWeekRule(FourWeekRuleParams::default());

    let num_candles = 525600;
    let mut candles = Vec::with_capacity(num_candles);
    for i in 0..num_candles {
        candles.push(Candle {
            time: i as u64 * time::MIN_MS,
            open: 0.0,
            high: 0.0,
            low: 0.0,
            close: i as f64,
            volume: i as f64,
        });
    }
    let fees = Fees {
        maker: 0.001,
        taker: 0.001,
    };
    let filters = Filters {
        price: Price {
            min: 0.0,
            max: 0.0,
            step: 0.0,
        },
        size: Size {
            min: 0.0,
            max: 0.0,
            step: 0.0,
        },
        base_precision: 8,
        quote_precision: 8,
    };
    let borrow_info = BorrowInfo {
        daily_interest_rate: 0.001,
        limit: 1.0,
    };
    let interval_offsets = HashMap::new();
    c.bench_function("trade", |b| {
        b.iter(|| {
            trading::trade(
                &TradingParams {
                    strategy,
                    stop_loss: StopLossParams::Noop(stop_loss::NoopParams {}),
                    take_profit: TakeProfitParams::Noop(take_profit::NoopParams {}),
                    trader: TraderParams {
                        interval: time::MIN_MS,
                        missed_candle_policy: MissedCandlePolicy::Ignore,
                    },
                },
                &candles,
                &fees,
                &filters,
                &borrow_info,
                &interval_offsets,
                2,
                1.0,
                true,
                true,
            )
        })
    });
}

criterion_group!(benches, trade_benchmark);
criterion_main!(benches);

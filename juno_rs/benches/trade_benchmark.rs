use criterion::{criterion_group, criterion_main, Criterion};
use juno_rs::{
    filters::{Filters, Price, Size},
    stop_loss,
    strategies::{FourWeekRule, FourWeekRuleParams},
    take_profit, trading, BorrowInfo, Candle, Fees,
};

const MIN_MS: u64 = 60000;

fn trade_benchmark(c: &mut Criterion) {
    let strategy_params = FourWeekRuleParams::default();

    let num_candles = 525600;
    let mut candles = Vec::with_capacity(num_candles);
    for i in 0..num_candles {
        candles.push(Candle {
            time: i as u64 * MIN_MS,
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
    c.bench_function("trade", |b| {
        b.iter(|| {
            trading::trade::<FourWeekRule, stop_loss::Noop, take_profit::Noop>(
                &strategy_params,
                &stop_loss::NoopParams {},
                &take_profit::NoopParams {},
                &candles,
                &fees,
                &filters,
                &borrow_info,
                2,
                60000,
                1.0,
                trading::MISSED_CANDLE_POLICY_IGNORE,
                true,
                true,
            )
        })
    });
}

criterion_group!(benches, trade_benchmark);
criterion_main!(benches);

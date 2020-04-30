use criterion::{criterion_group, criterion_main, Criterion};
use juno_rs::{
    BorrowInfo,
    Candle,
    Fees,
    filters::{Filters, Price, Size},
    strategies::MAMACX,
    trade::trade,
};

const MIN_MS: u64 = 60000;

// Adler32 of lowercased indicator name.
const EMA: u32 = 40698164;

fn trade_benchmark(c: &mut Criterion) {
    let strategy_factory = || { MAMACX::new(9, 24, -0.1, 0.1, 0, EMA, EMA) };
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
    c.bench_function("trade", |b| b.iter(|| trade(
        strategy_factory,
        &candles,
        &fees,
        &filters,
        &borrow_info,
        3,
        60000,
        1.0,
        0,
        0.0,
        true,
        true,
    )));
}

criterion_group!(benches, trade_benchmark);
criterion_main!(benches);

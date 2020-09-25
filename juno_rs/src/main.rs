use juno_rs::{genetics, indicators, prelude::*, statistics, storages, strategies, traders};

pub fn unpack(value: &str) -> (&str, &str) {
    let dash_i = value.find('-').unwrap();
    (&value[dash_i..], &value[0..dash_i])
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let exchange = "binance";
    let symbols = ["eth-btc", "ltc-btc", "xrp-btc"];
    let interval = HOUR_MS;
    let start = "2017-11-10".to_timestamp();
    let end = "2020-09-25".to_timestamp();
    let quote = 1.0;

    let algo = genetics::GeneticAlgorithm::new(
        genetics::evaluation::BasicEvaluation::<strategies::TripleMA>::new(
            exchange, &symbols, interval, start, end, quote,
        )?,
        genetics::selection::EliteSelection {},
        genetics::crossover::UniformCrossover::default(),
        genetics::mutation::UniformMutation::default(),
    );
    algo.evolve();
    Ok(())
}

// fn main() -> Result<(), Box<dyn std::error::Error>> {
//     let exchange = "binance";
//     let symbol = "eth-btc";
//     let interval = DAY_MS;
//     let quote = 1.0;

//     let (_, base_asset) = unpack(symbol);
//     let candles = storages::list_candles(
//         exchange,
//         symbol,
//         DAY_MS,
//         "2019-01-01".to_timestamp(),
//         "2020-01-01".to_timestamp(),
//     )?;
//     let exchange_info = storages::get_exchange_info(exchange)?;

//     let summary = traders::trade::<strategies::FourWeekRule>(
//         &strategies::FourWeekRuleParams {
//             period: 28,
//             ma: indicators::adler32::KAMA,
//             ma_period: 14,
//             mid_trend_policy: strategies::MidTrend::POLICY_IGNORE,
//         },
//         &candles,
//         &exchange_info.fees[symbol],
//         &exchange_info.filters[symbol],
//         &exchange_info.borrow_info[symbol][base_asset],
//         2,
//         interval,
//         quote,
//         traders::MISSED_CANDLE_POLICY_IGNORE,
//         0.13,
//         true,
//         0.0,
//         true,
//         true,
//     );
//     println!("summary {:?}", summary);
//     println!(
//         "sharpe {}",
//         statistics::calculate_sharpe_ratio(&summary, &candles, interval)?
//     );
//     Ok(())
// }

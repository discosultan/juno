#![allow(dead_code)]

use juno_rs::{
    fill_missing_candles, genetics, indicators, prelude::*, statistics, storages, strategies,
    traders,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    optimize()
    // backtest()
}

fn optimize() -> Result<(), Box<dyn std::error::Error>> {
    let exchange = "binance";
    let symbols = ["eth-btc", "ltc-btc", "xrp-btc"];
    // let symbols = ["eth-btc"];
    let interval = HOUR_MS;
    let start = "2017-11-10".to_timestamp();
    let end = "2020-09-30".to_timestamp();
    let quote = 1.0;

    let algo = genetics::GeneticAlgorithm::new(
        genetics::evaluation::BasicEvaluation::<strategies::TripleMA>::new(
            exchange, &symbols, interval, start, end, quote,
        )?,
        genetics::selection::EliteSelection::default(),
        // genetics::crossover::UniformCrossover::default(),
        genetics::crossover::UniformCrossover::new(0.75),
        // genetics::mutation::UniformMutation::default(),
        genetics::mutation::UniformMutation::new(0.25),
        genetics::reinsertion::EliteReinsertion::default(),
    );
    let population_size = 128;
    let generations = 32;
    let best_individual = algo.evolve(population_size, generations, Some(1));
    println!("{:?}", best_individual);

    let symbol_fitnesses = algo.evaluation.evaluate_symbols(&best_individual.chromosome);
    for (symbol, fitness) in symbols.iter().zip(symbol_fitnesses) {
        println!("{} - {:?}", symbol, fitness);
    }

    Ok(())
}

fn backtest() -> Result<(), Box<dyn std::error::Error>> {
    let exchange = "binance";
    let symbol = "xrp-btc";
    let interval = DAY_MS;
    let start = "2018-01-01".to_timestamp();
    let end = "2020-01-01".to_timestamp();
    let quote = 1.0;

    let candles = storages::list_candles(exchange, symbol, DAY_MS, start, end)?;
    let exchange_info = storages::get_exchange_info(exchange)?;

    let summary = traders::trade::<strategies::FourWeekRule>(
        &strategies::FourWeekRuleParams {
            period: 28,
            ma: indicators::adler32::KAMA,
            ma_period: 14,
            mid_trend_policy: strategies::MidTrend::POLICY_IGNORE,
        },
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        interval,
        quote,
        traders::MISSED_CANDLE_POLICY_IGNORE,
        0.13,
        true,
        0.0,
        true,
        true,
    );
    // println!("summary {:?}", summary);

    let candles_missing_filled = fill_missing_candles(interval, start, end, &candles);
    let base_prices: Vec<f64> = candles_missing_filled
        .iter()
        .map(|candle| candle.close)
        .collect();
    println!(
        "sharpe ratio {}",
        statistics::get_sharpe_ratio(&summary, &base_prices, None, interval)
    );
    let stats = statistics::analyse(&base_prices, None, &[], &summary, interval);
    println!("old sharpe ratio {}", stats.sharpe_ratio);
    Ok(())
}

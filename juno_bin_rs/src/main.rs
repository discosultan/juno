#![allow(dead_code)]

use juno_rs::{
    fill_missing_candles,
    genetics::{
        crossover, evaluation, mutation, reinsertion, selection, GeneticAlgorithm, Individual, TradingChromosome
    },
    prelude::*,
    statistics, storages,
    strategies::{self, Strategy},
    tactics, traders,
};
use prettytable::{Table, Row, Cell};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

struct Params {
    exchange: &'static str,
    interval: u64,
    start: u64,
    end: u64,
    quote: f64,
}

fn main() -> Result<()> {
    let args = Params {
        exchange: "binance",
        interval: HOUR_MS,
        start: "2017-12-08".to_timestamp(),
        end: "2020-09-30".to_timestamp(),
        quote: 1.0,
    };
    let symbols = vec!["eth-btc", "ltc-btc", "xrp-btc", "xmr-btc"];

    // TODO: support validating against arbitrary threshold.
    // TODO: Test out sortino ratio and impl sterling ratio calc.
    // TODO: Print out trading summaries.
    // optimize::<strategies::Cx<tactics::DoubleMA>>()?;
    // optimize::<strategies::Cx<tactics::TripleMA>>()?;
    // optimize::<strategies::CxOsc<tactics::SingleMA, tactics::Rsi>>()?;
    optimize::<strategies::CxOsc<tactics::TripleMA, tactics::Rsi>>(&args, &symbols)?;

    // let chromosome = TradingChromosome {
    //     trader: TraderParams {
    //         missed_candle_policy: traders::MISSED_CANDLE_POLICY_IGNORE,
    //         stop_loss: 0.13,
    //         trail_stop_loss: true,
    //         take_profit: 0.0,
    //     },
    //     strategy: strategies::FourWeekRuleParams {
    //         period: 28,
    //         ma: indicators::adler32::KAMA,
    //         ma_period: 14,
    //         mid_trend_policy: strategies::MidTrend::POLICY_IGNORE,
    //     },
    // };
    // backtest::<strategies::FourWeekRule>(&args, "eth-btc", &chromosome)?;

    Ok(())
}

fn optimize<T: Strategy>(args: &Params, symbols: &[&str]) -> Result<()> {
    let algo = GeneticAlgorithm::new(
        evaluation::BasicEvaluation::<T>::new(
            args.exchange, symbols, args.interval, args.start, args.end, args.quote
        )?,
        selection::EliteSelection::default(),
        // selection::TournamentSelection::default(),
        // crossover::UniformCrossover::default(),
        crossover::UniformCrossover::new(0.75),
        // mutation::UniformMutation::default(),
        mutation::UniformMutation::new(0.25),
        // reinsertion::EliteReinsertion::default(),
        reinsertion::EliteReinsertion::new(0.75),
    );
    let population_size = 512;
    let generations = 64;
    let seed = Some(1);
    let gens = algo.evolve(population_size, generations, seed);

    // print_best_individual::<T>(args, symbols, &gens);
    print_all_generations::<T>(args, symbols, &gens);

    Ok(())
}

fn print_best_individual<T: Strategy>(
    args: &Params, symbols: &[&str], gens: &[Individual<TradingChromosome<T::Params>>]
) {
    let best_individual = &gens[gens.len() - 1];

    let symbol_fitnesses: Vec<f64> = symbols
        .iter()
        .map(|symbol| backtest::<T>(args, symbol, &best_individual.chromosome).unwrap())
        .collect();

    println!("strategy {}", std::any::type_name::<T>());
    println!("interval {}", args.interval.to_interval_str());
    println!("best individual {:?}", best_individual);
    symbols
        .iter()
        .zip(symbol_fitnesses)
        .for_each(|(symbol, fitness)| println!("{} sharpe ratio - {}", symbol, fitness));
}

fn print_all_generations<T: Strategy>(
    args: &Params, symbols: &[&str], gens: &[Individual<TradingChromosome<T::Params>>]
) {
    let mut table = Table::new();
    let mut cells = vec![Cell::new("")];
    symbols
        .iter()
        .for_each(|symbol| cells.push(Cell::new(&format!("{} sharpe", symbol))));
    cells.push(Cell::new("fitness"));
    table.add_row(Row::new(cells));

    let mut last_fitness = f64::NAN;
    for (i, ind) in gens.iter().enumerate() {
        if ind.fitness == last_fitness {
            continue;
        }

        let symbol_fitnesses: Vec<f64> = symbols
            .iter()
            .map(|symbol| backtest::<T>(args, symbol, &ind.chromosome).unwrap())
            .collect();
        let mut cells = vec![Cell::new(&(i + 1).to_string())];
        symbol_fitnesses
            .iter()
            .for_each(|fitness| cells.push(Cell::new(&fitness.to_string())));
        cells.push(Cell::new(&ind.fitness.to_string()));
        table.add_row(Row::new(cells));

        last_fitness = ind.fitness;
    }

    println!("strategy {}", std::any::type_name::<T>());
    println!("interval {}", args.interval.to_interval_str());
    table.printstd();
}

fn backtest<T: Strategy>(
    args: &Params, symbol: &str, chrom: &TradingChromosome<T::Params>
) -> Result<f64> {
    let candles = storages::list_candles(
        args.exchange, symbol, args.interval, args.start, args.end
    )?;
    let exchange_info = storages::get_exchange_info(args.exchange)?;

    let summary = traders::trade::<T>(
        &chrom.strategy,
        &candles,
        &exchange_info.fees[symbol],
        &exchange_info.filters[symbol],
        &exchange_info.borrow_info[symbol][symbol.base_asset()],
        2,
        args.interval,
        args.quote,
        chrom.trader.missed_candle_policy,
        chrom.trader.stop_loss,
        chrom.trader.trail_stop_loss,
        chrom.trader.take_profit,
        true,
        true,
    );
    // println!("summary {:?}", summary);

    let stats_interval = DAY_MS;
    let stats_candles = storages::list_candles(
        args.exchange, symbol, stats_interval, args.start, args.end
    )?;
    let candles_missing_filled = fill_missing_candles(
        stats_interval, args.start, args.end, &stats_candles
    );
    let base_prices: Vec<f64> = candles_missing_filled
        .iter()
        .map(|candle| candle.close)
        .collect();
    // let stats = statistics::analyse(&base_prices, None, &[], &summary, args.interval);
    // println!("old sharpe ratio {}", stats.sharpe_ratio);

    Ok(statistics::get_sharpe_ratio(&summary, &base_prices, None, stats_interval))
}

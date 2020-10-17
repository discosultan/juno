#![allow(dead_code)]

use juno_rs::{
    fill_missing_candles,
    genetics::{crossover, mutation, reinsertion, selection, GeneticAlgorithm, Individual},
    prelude::*,
    statistics, storages,
    strategies::*,
    trading::{self, TradingChromosome, TradingSummary},
};
use prettytable::{Cell, Row, Table};

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
        interval: HOUR_MS * 8,
        start: "2017-12-08".to_timestamp(),
        end: "2020-09-30".to_timestamp(),
        quote: 1.0,
    };
    let symbols = vec!["eth-btc", "ltc-btc", "xrp-btc", "xmr-btc"];
    let validation_symbols = vec!["ada-btc"];

    // TODO: support validating against arbitrary threshold.
    // TODO: Test out sortino ratio and impl sterling ratio calc.
    // TODO: Print out trading summaries.
    optimize_validate_print::<SigOsc<TripleMA, Rsi>>(&args, &symbols, &validation_symbols)?;

    // let chromosome = TradingChromosome {
    //     trader: TraderParams {
    //         missed_candle_policy: traders::MISSED_CANDLE_POLICY_IGNORE,
    //         stop_loss: 0.13,
    //         trail_stop_loss: true,
    //         take_profit: 0.0,
    //     },
    //     strategy: FourWeekRuleParams {
    //         period: 28,
    //         ma: indicators::adler32::KAMA,
    //         ma_period: 14,
    //         mid_trend_policy: MidTrend::POLICY_IGNORE,
    //     },
    // };
    // backtest::<FourWeekRule>(&args, "eth-btc", &chromosome)?;
    // let chromosome = TradingChromosome {
    //     trader: TraderParams {
    //         missed_candle_policy: 0,
    //         stop_loss: 0.9669264261498001,
    //         trail_stop_loss: true,
    //         take_profit: 0.0,
    //     },
    //     strategy: SigOscParams {
    //         cx_params: TripleMAParams {
    //             short_ma: 72483247,
    //             medium_ma: 66978200,
    //             long_ma: 68026779,
    //             periods: (35, 48, 97),
    //         },
    //         osc_params: RsiParams {
    //             period: 88,
    //             up_threshold: 64.11491594864773,
    //             down_threshold: 34.31436808000039,
    //         },
    //     },
    // };
    // backtest::<SigOsc<TripleMA, Rsi>>(&args, "eth-btc", &chromosome)?;

    Ok(())
}

fn optimize_validate_print<T: Signal>(
    args: &Params,
    symbols: &[&str],
    validation_symbols: &[&str],
) -> Result<()> {
    // Optimize.
    let gens = optimize::<T>(&args, &symbols)?;

    // print_individual::<T>(args, symbols, &gens[gens.len() - 1]);  // Best.
    print_all_generations::<T>(&args, &symbols, &validation_symbols, &gens);

    Ok(())
}

fn optimize<T: Signal>(
    args: &Params,
    symbols: &[&str],
) -> Result<Vec<Individual<TradingChromosome<T::Params>>>> {
    let algo = GeneticAlgorithm::new(
        trading::BasicEvaluation::<T>::new(
            args.exchange,
            symbols,
            args.interval,
            args.start,
            args.end,
            args.quote,
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
    let generations = 128;
    let seed = Some(1);
    let gens = algo.evolve(population_size, generations, seed);
    Ok(gens)
}

fn print_individual<T: Signal>(
    args: &Params,
    symbols: &[&str],
    individual: &Individual<TradingChromosome<T::Params>>,
) {
    let symbol_fitnesses: Vec<f64> = symbols
        .iter()
        .map(|symbol| {
            backtest::<T>(args, symbol, &individual.chromosome)
                .unwrap()
                .0
        })
        .collect();

    println!("strategy {}", std::any::type_name::<T>());
    println!("interval {}", args.interval.to_interval_str());
    println!("individual {:?}", individual);
    symbols
        .iter()
        .zip(symbol_fitnesses)
        .for_each(|(symbol, fitness)| println!("{} sharpe ratio - {}", symbol, fitness));
}

fn print_all_generations<T: Signal>(
    args: &Params,
    symbols: &[&str],
    validation_symbols: &[&str],
    gens: &[Individual<TradingChromosome<T::Params>>],
) {
    let mut table = Table::new();
    let mut cells = vec![Cell::new("")];
    symbols
        .iter()
        .for_each(|symbol| cells.push(Cell::new(&format!("{} sharpe", symbol))));
    validation_symbols
        .iter()
        .for_each(|symbol| cells.push(Cell::new(&format!("{} sharpe (v)", symbol))));
    cells.push(Cell::new("fitness"));
    table.add_row(Row::new(cells));

    let mut last_fitness = f64::NAN;
    for (i, ind) in gens.iter().enumerate() {
        if ind.fitness == last_fitness {
            continue;
        }

        // Gen number.
        let mut cells = vec![Cell::new(&i.to_string())];

        // TODO: temp
        if i == 47 {
            println!("ind {:?}", ind);
        }
        // Training + validation symbol results.
        symbols
            .iter()
            .chain(validation_symbols)
            .map(|symbol| backtest::<T>(args, symbol, &ind.chromosome).unwrap())
            .for_each(|(sharpe, summary)| {
                cells.push(Cell::new(&sharpe.to_string()));
                // TODO: temp
                if i == 47 {
                    println!("summary {:?}", summary);
                    println!("sharpe {}", sharpe);
                }
            });

        // Fitness.
        cells.push(Cell::new(&ind.fitness.to_string()));

        table.add_row(Row::new(cells));

        last_fitness = ind.fitness;
    }

    println!("strategy {}", std::any::type_name::<T>());
    println!("interval {}", args.interval.to_interval_str());
    table.printstd();
}

fn backtest<T: Signal>(
    args: &Params,
    symbol: &str,
    chrom: &TradingChromosome<T::Params>,
) -> Result<(f64, TradingSummary)> {
    let candles =
        storages::list_candles(args.exchange, symbol, args.interval, args.start, args.end)?;
    let exchange_info = storages::get_exchange_info(args.exchange)?;

    let result = trading::trade::<T>(
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

    let stats_interval = DAY_MS;
    let stats_candles =
        storages::list_candles(args.exchange, symbol, stats_interval, args.start, args.end)?;
    let candles_missing_filled =
        fill_missing_candles(stats_interval, args.start, args.end, &stats_candles);
    let base_prices: Vec<f64> = candles_missing_filled
        .iter()
        .map(|candle| candle.close)
        .collect();

    // let stats = statistics::analyse(&base_prices, None, &[], &result, args.interval);
    // let sharpe = stats.sharpe_ratio;

    let summary = result.get_summary();
    let sharpe = statistics::get_sharpe_ratio(&result, &base_prices, None, stats_interval);

    Ok((sharpe, summary))
}
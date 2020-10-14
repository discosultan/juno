use super::TradingChromosome;
use crate::{
    common::{BorrowInfo, Candle, Fees, Filters},
    fill_missing_candles,
    genetics::{Evaluation, Individual},
    statistics, storages,
    strategies::Signal,
    time, trading, SymbolExt,
};
use rayon::prelude::*;
use std::{error::Error, marker::PhantomData};

struct SymbolCtx {
    candles: Vec<Candle>,
    fees: Fees,
    filters: Filters,
    borrow_info: BorrowInfo,
    stats_base_prices: Vec<f64>,
}

pub struct BasicEvaluation<T: Signal> {
    symbol_ctxs: Vec<SymbolCtx>,
    interval: u64,
    quote: f64,
    stats_interval: u64,
    phantom: PhantomData<T>,
}

impl<T: Signal> BasicEvaluation<T> {
    pub fn new(
        exchange: &str,
        symbols: &[&str],
        interval: u64,
        start: u64,
        end: u64,
        quote: f64,
    ) -> Result<Self, Box<dyn Error>> {
        let exchange_info = storages::get_exchange_info(exchange)?;
        let stats_interval = time::DAY_MS;
        let symbol_ctxs = symbols
            .iter()
            .map(|&symbol| {
                let candles =
                    storages::list_candles(exchange, symbol, interval, start, end).unwrap();
                // TODO: Do listing and filling of missing candles in one go?
                let stats_candles =
                    storages::list_candles(exchange, symbol, stats_interval, start, end).unwrap();
                let stats_candles =
                    fill_missing_candles(stats_interval, start, end, &stats_candles);
                let stats_prices: Vec<f64> =
                    stats_candles.iter().map(|candle| candle.close).collect();
                SymbolCtx {
                    candles,
                    fees: exchange_info.fees[symbol],
                    filters: exchange_info.filters[symbol],
                    borrow_info: exchange_info.borrow_info[symbol][symbol.base_asset()],
                    stats_base_prices: stats_prices,
                }
            })
            .collect();

        Ok(Self {
            symbol_ctxs,
            interval,
            stats_interval,
            quote,
            phantom: PhantomData,
        })
    }

    pub fn evaluate_symbols(&self, chromosome: &TradingChromosome<T::Params>) -> Vec<f64> {
        self.symbol_ctxs
            .par_iter()
            .map(|ctx| self.evaluate_symbol(ctx, chromosome))
            .collect()
    }

    fn evaluate_symbol(&self, ctx: &SymbolCtx, chromosome: &TradingChromosome<T::Params>) -> f64 {
        let summary = trading::trade::<T>(
            &chromosome.strategy,
            &ctx.candles,
            &ctx.fees,
            &ctx.filters,
            &ctx.borrow_info,
            2,
            self.interval,
            self.quote,
            chromosome.trader.missed_candle_policy,
            chromosome.trader.stop_loss,
            chromosome.trader.trail_stop_loss,
            chromosome.trader.take_profit,
            true,
            true,
        );
        let sharpe_ratio = statistics::get_sharpe_ratio(
            &summary,
            &ctx.stats_base_prices,
            None,
            self.stats_interval,
        );
        // TODO: get rid of this as well
        assert!(!sharpe_ratio.is_nan());
        sharpe_ratio
    }
}

impl<T: Signal> Evaluation for BasicEvaluation<T> {
    type Chromosome = TradingChromosome<T::Params>;

    fn evaluate(&self, population: &mut [Individual<Self::Chromosome>]) {
        // TODO: Support different strategies here. A la parallel cpu or gpu, for example.
        // let fitnesses = Vec::with_capacity(population.len());
        // let fitness_slices = fitnesses.chunks_exact_mut(1).collect();
        population
            // .iter_mut()
            .par_iter_mut()
            .for_each(|ind| {
                ind.fitness = self
                    .symbol_ctxs
                    .iter()
                    .map(|ctx| self.evaluate_symbol(ctx, &ind.chromosome))
                    .fold(0.0, sum_log)
            });
    }
}

fn sum_linear(acc: f64, val: f64) -> f64 {
    acc + val
}
fn sum_log(acc: f64, val: f64) -> f64 {
    acc + if val > 0.0 {
        (val + 1.0).log10()
    } else {
        -(-val + 1.0).log10()
    }
}

use super::{Chromosome, Individual, TradingChromosome};
use crate::{common, statistics, storages, strategies::Strategy, traders};
use rayon::prelude::*;
use std::{error::Error, marker::PhantomData};

pub trait Evaluation {
    type Chromosome: Chromosome;

    fn evaluate(&self, population: &mut [Individual<Self::Chromosome>]);
}

struct SymbolCtx {
    candles: Vec<common::Candle>,
    fees: common::Fees,
    filters: common::Filters,
    borrow_info: common::BorrowInfo,
}

pub struct BasicEvaluation<T: Strategy> {
    symbol_ctxs: Vec<SymbolCtx>,
    interval: u64,
    quote: f64,
    phantom: PhantomData<T>,
}

impl<T: Strategy> BasicEvaluation<T> {
    pub fn new(
        exchange: &str,
        symbols: &[&str],
        interval: u64,
        start: u64,
        end: u64,
        quote: f64,
    ) -> Result<Self, Box<dyn Error>> {
        let exchange_info = storages::get_exchange_info(exchange)?;
        let symbol_ctxs = symbols
            .iter()
            .map(|&symbol| {
                let dash_i = symbol.find('-').unwrap();
                let base_asset = &symbol[0..dash_i];
                SymbolCtx {
                    candles: storages::list_candles(exchange, symbol, interval, start, end)
                        .unwrap(),
                    fees: exchange_info.fees[symbol],
                    filters: exchange_info.filters[symbol],
                    borrow_info: exchange_info.borrow_info[symbol][base_asset],
                }
            })
            .collect();

        Ok(Self {
            symbol_ctxs,
            interval,
            quote,
            phantom: PhantomData,
        })
    }

    fn evaluate_individual(&self, ind: &mut Individual<TradingChromosome<T::Params>>) {
        ind.fitness = self
            .symbol_ctxs
            .iter()
            .map(|ctx| {
                let summary = traders::trade::<T>(
                    &ind.chromosome.strategy,
                    &ctx.candles,
                    &ctx.fees,
                    &ctx.filters,
                    &ctx.borrow_info,
                    2,
                    self.interval,
                    self.quote,
                    ind.chromosome.trader.missed_candle_policy,
                    ind.chromosome.trader.stop_loss,
                    ind.chromosome.trader.trail_stop_loss,
                    ind.chromosome.trader.take_profit,
                    true,
                    true,
                );
                statistics::calculate_sharpe_ratio(&summary, &ctx.candles, self.interval).unwrap()
            })
            .fold(0.0, linear);
        // TODO: get rid of this as well
        assert!(!ind.fitness.is_nan());
    }
}

impl<T: Strategy> Evaluation for BasicEvaluation<T> {
    type Chromosome = TradingChromosome<T::Params>;

    fn evaluate(&self, population: &mut [Individual<Self::Chromosome>]) {
        // TODO: Support different strategies here. A la parallel cpu or gpu, for example.
        // let fitnesses = Vec::with_capacity(population.len());
        // let fitness_slices = fitnesses.chunks_exact_mut(1).collect();
        population
            // .iter_mut()
            .par_iter_mut()
            .for_each(|ind| self.evaluate_individual(ind));
    }
}

fn linear(acc: f64, val: f64) -> f64 {
    acc + val
}
fn ln(acc: f64, val: f64) -> f64 {
    acc + val.ln()
}

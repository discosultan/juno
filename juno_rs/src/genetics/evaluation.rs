use super::{Chromosome, Individual, TradingChromosome};
use crate::{
    common::{BorrowInfo, Candle, Fees, Filters},
    math::floor_multiple,
    statistics,
    storages,
    strategies::Strategy,
    time,
    traders,
};
use rayon::prelude::*;
use std::{error::Error, marker::PhantomData};

pub trait Evaluation {
    type Chromosome: Chromosome;

    fn evaluate(&self, population: &mut [Individual<Self::Chromosome>]);
}

struct SymbolCtx {
    candles: Vec<Candle>,
    fees: Fees,
    filters: Filters,
    borrow_info: BorrowInfo,
    stats_base_prices: Vec<f64>,
}

pub struct BasicEvaluation<T: Strategy> {
    symbol_ctxs: Vec<SymbolCtx>,
    interval: u64,
    quote: f64,
    stats_interval: u64,
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
        let stats_interval = time::DAY_MS;
        let symbol_ctxs = symbols
            .iter()
            .map(|&symbol| {
                let dash_i = symbol.find('-').unwrap();
                let base_asset = &symbol[0..dash_i];
                let candles = storages::list_candles(exchange, symbol, interval, start, end)
                    .unwrap();
                // TODO: Do listing and filling of missing candles in one go.
                let stats_candles = storages::list_candles(
                    exchange, symbol, stats_interval, start, end
                ).unwrap();
                let stats_candles = fill_missing_candles(stats_interval, start, end, &stats_candles);
                let stats_prices: Vec<f64> = stats_candles
                    .iter()
                    .map(|candle| candle.close)
                    .collect();
                SymbolCtx {
                    candles,
                    fees: exchange_info.fees[symbol],
                    filters: exchange_info.filters[symbol],
                    borrow_info: exchange_info.borrow_info[symbol][base_asset],
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
                statistics::get_sharpe_ratio(
                    &summary, &ctx.stats_base_prices, None, self.stats_interval
                )
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

fn fill_missing_candles(interval: u64, start: u64, end: u64, candles: &[Candle]) -> Vec<Candle> {
    let start = floor_multiple(start, interval);
    let end = floor_multiple(end, interval);
    let length = ((end - start) / interval) as usize;

    let mut candles_filled = Vec::with_capacity(length);
    let mut current = start;
    let mut prev_candle: Option<&Candle> = None;

    for candle in candles {
        let mut diff = (candle.time - current) / interval;
        for i in 1..=diff {
            diff -= 1;
            match prev_candle {
                None => panic!("missing first candle in period; cannot fill"),
                Some(ref c) => candles_filled.push(Candle {
                    time: c.time + i as u64 * interval,
                    open: c.open,
                    high: c.high,
                    low: c.low,
                    close: c.close,
                    volume: c.volume,
                }),
            }
            current += interval;
        }

        candles_filled.push(*candle);
        current += interval;

        prev_candle = Some(candle);
    }

    assert_eq!(candles_filled.len(), length);
    candles_filled
}

// use rayon::prelude::*;
use crate::{common, storages, statistics, strategies::Strategy, traders};
use super::Individual;

struct SymbolCtx {
    candles: Vec<common::Candle>,
    fees: common::Fees,
    filters: common::Filters,
    borrow_info: common::BorrowInfo,
}
pub struct Evaluation {
    symbol_ctxs: Vec<SymbolCtx>,
    interval: u64,
    quote: f64,
}

impl Evaluation {
    pub fn new(
        exchange: &str, symbols: &[&str], interval: u64, start: u64, end: u64, quote: f64
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let exchange_info = storages::get_exchange_info(exchange)?;
        let symbol_ctxs = symbols
            .iter()
            .map(|&symbol| {
                let dash_i = symbol.find('-').unwrap();
                let base_asset = &symbol[0..dash_i];
                SymbolCtx {
                    candles: storages::list_candles(exchange, symbol, interval, start, end).unwrap(),
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
        })
    }

    pub fn evaluate<T: Strategy>(&self, population: &Vec<Individual<T::Params>>) -> Vec<f64> {
        // TODO: Support different strategies here. A la parallel cpu or gpu, for example.
        // let fitnesses = Vec::with_capacity(population.len());
        // let fitness_slices = fitnesses.chunks_exact_mut(1).collect();
        population
            .iter()
            .map(|ind| self.evaluate_individual::<T>(ind))
            .collect()
    }

    fn evaluate_individual<T: Strategy>(&self, ind: &Individual<T::Params>) -> f64 {
        self.symbol_ctxs
            .iter()
            .map(|ctx| {
                let summary = traders::trade::<T>(
                    &ind.strategy,
                    &ctx.candles,
                    &ctx.fees,
                    &ctx.filters,
                    &ctx.borrow_info,
                    2,
                    self.interval,
                    self.quote,
                    ind.trader.missed_candle_policy,
                    ind.trader.stop_loss,
                    ind.trader.trail_stop_loss,
                    ind.trader.take_profit,
                    true,
                    true,
                );
                statistics::calculate_sharpe_ratio(&summary, &ctx.candles, self.interval).unwrap()
            })
            .fold(0.0, linear)
    }
}

fn linear(acc: f64, val: f64) -> f64 { acc + val }
fn ln(acc: f64, val: f64) -> f64 { acc + val.ln() }

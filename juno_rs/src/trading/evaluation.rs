use super::TradingParams;
use crate::{
    chandler::{candles_to_prices, fill_missing_candles},
    genetics::{Evaluation, Individual},
    statistics,
    stop_loss::StopLoss,
    storages,
    strategies::Signal,
    take_profit::TakeProfit,
    time,
    trading::trade,
    BorrowInfo, Candle, Fees, Filters, SymbolExt,
};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, marker::PhantomData};

#[derive(Clone, Copy, Deserialize, Serialize)]
pub enum EvaluationStatistic {
    Profit,
    ReturnOverMaxDrawdown,
    SharpeRatio,
    SortinoRatio,
}

impl EvaluationStatistic {
    pub fn values() -> [Self; 4] {
        [
            Self::Profit,
            Self::ReturnOverMaxDrawdown,
            Self::SharpeRatio,
            Self::SortinoRatio,
        ]
    }
}

#[derive(Clone, Copy, Deserialize, Serialize)]
pub enum EvaluationAggregation {
    Linear,
    Log10,
    Log10Factored,
}

impl EvaluationAggregation {
    pub fn values() -> [Self; 3] {
        [Self::Linear, Self::Log10, Self::Log10Factored]
    }
}

struct SymbolCtx {
    interval_candles: HashMap<u64, Vec<Candle>>,
    fees: Fees,
    filters: Filters,
    borrow_info: BorrowInfo,
    stats_base_prices: Vec<f64>,
    stats_quote_prices: Option<Vec<f64>>,
}

pub struct BasicEvaluation<T: Signal, U: StopLoss, V: TakeProfit> {
    symbol_ctxs: Vec<SymbolCtx>,
    // interval: u64,
    quote: f64,
    stats_interval: u64,
    evaluation_statistic: EvaluationStatistic,
    evaluation_aggregation_fn: fn(f64, f64) -> f64,
    signal_phantom: PhantomData<T>,
    stop_loss_phantom: PhantomData<U>,
    take_profit_phantom: PhantomData<V>,
}

impl<T: Signal, U: StopLoss, V: TakeProfit> BasicEvaluation<T, U, V> {
    pub fn new(
        exchange: &str,
        symbols: &[String],
        intervals: &[u64],
        start: u64,
        end: u64,
        quote: f64,
        evaluation_statistic: EvaluationStatistic,
        evaluation_aggregation: EvaluationAggregation,
    ) -> Result<Self, storages::StorageError> {
        let exchange_info = storages::get_exchange_info(exchange)?;
        let stats_interval = time::DAY_MS;
        let symbol_ctxs = symbols
            .iter()
            .map(|symbol| {
                let interval_candles: HashMap<u64, Vec<Candle>> = intervals
                    .iter()
                    .map(|&interval| {
                        (
                            interval,
                            storages::list_candles(exchange, &symbol, interval, start, end)
                                .unwrap(),
                        )
                    })
                    .collect();
                // TODO: Do listing and filling of missing candles in one go?

                // Stats base.
                let stats_candles =
                    storages::list_candles(exchange, &symbol, stats_interval, start, end).unwrap();
                let stats_candles =
                    fill_missing_candles(stats_interval, start, end, &stats_candles).unwrap();

                // Stats quote (optional).
                let stats_fiat_candles =
                    storages::list_candles("coinbase", "btc-eur", stats_interval, start, end)
                        .unwrap();
                let stats_fiat_candles =
                    fill_missing_candles(stats_interval, start, end, &stats_fiat_candles).unwrap();

                // let stats_quote_prices = None;
                let stats_quote_prices = Some(candles_to_prices(&stats_fiat_candles, None));
                let stats_base_prices =
                    candles_to_prices(&stats_candles, stats_quote_prices.as_deref());

                // Store context variables.
                SymbolCtx {
                    interval_candles,
                    fees: exchange_info.fees[symbol],
                    filters: exchange_info.filters[symbol],
                    borrow_info: exchange_info.borrow_info[symbol][symbol.base_asset()],
                    stats_base_prices,
                    stats_quote_prices,
                }
            })
            .collect();

        Ok(Self {
            symbol_ctxs,
            // intervals,
            stats_interval,
            quote,
            evaluation_statistic,
            evaluation_aggregation_fn: match evaluation_aggregation {
                EvaluationAggregation::Linear => sum_linear,
                EvaluationAggregation::Log10 => sum_log10,
                EvaluationAggregation::Log10Factored => sum_log10_factored,
            },
            signal_phantom: PhantomData,
            stop_loss_phantom: PhantomData,
            take_profit_phantom: PhantomData,
        })
    }

    pub fn evaluate_symbols(
        &self,
        chromosome: &TradingParams<T::Params, U::Params, V::Params>,
    ) -> Vec<f64> {
        self.symbol_ctxs
            .par_iter()
            .map(|ctx| self.evaluate_symbol(ctx, chromosome))
            .collect()
    }

    fn evaluate_symbol(
        &self,
        ctx: &SymbolCtx,
        chromosome: &TradingParams<T::Params, U::Params, V::Params>,
    ) -> f64 {
        let summary = trade::<T, U, V>(
            &chromosome.strategy,
            &chromosome.stop_loss,
            &chromosome.take_profit,
            &ctx.interval_candles[&chromosome.trader.interval],
            &ctx.fees,
            &ctx.filters,
            &ctx.borrow_info,
            2,
            chromosome.trader.interval,
            self.quote,
            chromosome.trader.missed_candle_policy,
            true,
            true,
        );
        match self.evaluation_statistic {
            EvaluationStatistic::Profit => statistics::get_profit(&summary),
            EvaluationStatistic::ReturnOverMaxDrawdown => {
                statistics::get_return_over_max_drawdown(&summary)
            }
            EvaluationStatistic::SharpeRatio => statistics::get_sharpe_ratio(
                &summary,
                &ctx.stats_base_prices,
                ctx.stats_quote_prices.as_deref(),
                self.stats_interval,
            ),
            EvaluationStatistic::SortinoRatio => statistics::get_sortino_ratio(
                &summary,
                &ctx.stats_base_prices,
                ctx.stats_quote_prices.as_deref(),
                self.stats_interval,
            ),
        }
    }
}

impl<T: Signal, U: StopLoss, V: TakeProfit> Evaluation for BasicEvaluation<T, U, V> {
    type Chromosome = TradingParams<T::Params, U::Params, V::Params>;

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
                    .fold(0.0, self.evaluation_aggregation_fn)
            });
    }
}

fn sum_linear(acc: f64, val: f64) -> f64 {
    acc + val
}
fn sum_log10(acc: f64, val: f64) -> f64 {
    const LOG_SHIFT_FACTOR: f64 = 1.0;
    acc + if val >= 0.0 {
        (val + LOG_SHIFT_FACTOR).log10()
    } else {
        -(-val + LOG_SHIFT_FACTOR).log10()
    }
}
fn sum_log10_factored(acc: f64, val: f64) -> f64 {
    const FACTOR: f64 = 10.0;
    sum_log10(acc, val * FACTOR)
}

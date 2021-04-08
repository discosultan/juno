use super::TradingParams;
use crate::{
    candles,
    genetics::{Evaluation, Individual},
    statistics, storage, time,
    trading::trade,
    BorrowInfo, Candle, Fees, Filters, SymbolExt,
};
use futures::future::{try_join3, try_join_all};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;

type Result<T> = std::result::Result<T, EvaluationError>;

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

#[derive(Error, Debug)]
pub enum EvaluationError {
    #[error("{0}")]
    Storage(#[from] storage::Error),
    #[error("{0}")]
    Chandler(#[from] candles::Error),
}

struct SymbolCtx {
    interval_candles: HashMap<u64, Vec<Candle>>,
    fees: Fees,
    filters: Filters,
    borrow_info: BorrowInfo,
    stats_base_prices: Vec<f64>,
    stats_quote_prices: Option<Vec<f64>>,
}

pub struct BasicEvaluation {
    symbol_ctxs: Vec<SymbolCtx>,
    quote: f64,
    interval_offsets: HashMap<u64, u64>,
    stats_interval: u64,
    evaluation_statistic: EvaluationStatistic,
    evaluation_aggregation_fn: fn(f64, f64) -> f64,
}

impl BasicEvaluation {
    pub async fn new(
        exchange: &str,
        symbols: &[String],
        intervals: &[u64],
        start: u64,
        end: u64,
        quote: f64,
        evaluation_statistic: EvaluationStatistic,
        evaluation_aggregation: EvaluationAggregation,
    ) -> Result<Self> {
        let exchange_info = storage::get_exchange_info(exchange).await?;
        let stats_interval = time::DAY_MS;
        let symbol_ctxs = try_join_all(symbols.iter().map(|symbol| (symbol, &exchange_info)).map(
            |(symbol, exchange_info)| async move {
                let interval_candles_task =
                    try_join_all(intervals.iter().map(|&interval| async move {
                        Ok::<_, candles::Error>((
                            interval,
                            candles::list_candles(exchange, &symbol, interval, start, end).await?,
                        ))
                    }));

                // Stats base.
                let stats_candles_task = candles::list_candles_fill_missing(
                    exchange,
                    &symbol,
                    stats_interval,
                    start,
                    end,
                );

                // Stats quote (optional).
                let stats_fiat_candles_task = candles::list_candles_fill_missing(
                    "binance",
                    "btc-usdt",
                    stats_interval,
                    start,
                    end,
                );

                let (interval_candles, stats_candles, stats_fiat_candles) = try_join3(
                    interval_candles_task,
                    stats_candles_task,
                    stats_fiat_candles_task,
                )
                .await?;

                let interval_candles = interval_candles.into_iter().collect();

                // let stats_quote_prices = None;
                let stats_quote_prices =
                    Some(candles::candles_to_prices(&stats_fiat_candles, None));
                let stats_base_prices =
                    candles::candles_to_prices(&stats_candles, stats_quote_prices.as_deref());

                // Store context variables.
                Ok::<_, candles::Error>(SymbolCtx {
                    interval_candles,
                    fees: exchange_info.fees[symbol],
                    filters: exchange_info.filters[symbol],
                    borrow_info: exchange_info.borrow_info[symbol][symbol.base_asset()],
                    stats_base_prices,
                    stats_quote_prices,
                })
            },
        ))
        .await?;

        Ok(Self {
            symbol_ctxs,
            interval_offsets: candles::map_interval_offsets(exchange),
            stats_interval,
            quote,
            evaluation_statistic,
            evaluation_aggregation_fn: match evaluation_aggregation {
                EvaluationAggregation::Linear => sum_linear,
                EvaluationAggregation::Log10 => sum_log10,
                EvaluationAggregation::Log10Factored => sum_log10_factored,
            },
        })
    }

    pub fn evaluate_symbols(&self, chromosome: &TradingParams) -> Vec<f64> {
        self.symbol_ctxs
            .par_iter()
            .map(|symbol_ctx| self.evaluate_symbol(symbol_ctx, chromosome))
            .collect()
    }

    fn evaluate_symbol(&self, symbol_ctx: &SymbolCtx, chromosome: &TradingParams) -> f64 {
        let summary = trade(
            &chromosome,
            &symbol_ctx.interval_candles[&chromosome.trader.interval],
            &symbol_ctx.fees,
            &symbol_ctx.filters,
            &symbol_ctx.borrow_info,
            &self.interval_offsets,
            2,
            self.quote,
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
                &symbol_ctx.stats_base_prices,
                symbol_ctx.stats_quote_prices.as_deref(),
                self.stats_interval,
            ),
            EvaluationStatistic::SortinoRatio => statistics::get_sortino_ratio(
                &summary,
                &symbol_ctx.stats_base_prices,
                symbol_ctx.stats_quote_prices.as_deref(),
                self.stats_interval,
            ),
        }
    }
}

impl Evaluation for BasicEvaluation {
    type Chromosome = TradingParams;

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
        // -(-val + LOG_SHIFT_FACTOR).log10()
        -(10.0_f64).powf(-val + LOG_SHIFT_FACTOR)
    }
}
fn sum_log10_factored(acc: f64, val: f64) -> f64 {
    const FACTOR: f64 = 10.0;
    sum_log10(acc, val * FACTOR)
}

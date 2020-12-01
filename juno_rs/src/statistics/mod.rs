mod optimized;
pub use optimized::*;

use crate::{
    math::{annualized, floor_multiple, mean, std_deviation},
    time::{serialize_interval, serialize_timestamp},
    trading::{CloseReason, Position, TradingSummary},
};
// use ndarray::prelude::*;
// use ndarray_stats::CorrelationExt;
use serde::Serialize;
use std::collections::HashMap;

pub type AnalysisResult = (f64,);

// TODO: Use const fn when `365.0.sqrt()` is supported.
pub(crate) const SQRT_365: f64 = 19.10497317454279908588432590477168560028076171875;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub(crate) enum Asset {
    Base,
    Quote,
}

pub struct Statistics {
    // performance: Vec<f64>,
    // a_returns: Vec<f64>,
    pub g_returns: Vec<f64>,
    // neg_g_returns: Vec<f64>,

    // total_return: f64,
    pub annualized_return: f64,
    // annualized_volatility: f64,
    // annualized_downside_risk: f64,
    pub sharpe_ratio: f64,
    pub sortino_ratio: f64,
    // cagr: f64,
}

pub fn analyse(
    summary: &TradingSummary,
    base_prices: &[f64],
    quote_prices: Option<&[f64]>,
    // _benchmark_g_returns: &[f64],
    interval: u64,
) -> Statistics {
    let asset_performance = get_asset_performance(summary, base_prices, quote_prices, interval);
    let portfolio_performance = asset_performance
        .iter()
        .map(|d| d.values().sum())
        .collect::<Vec<f64>>();
    calculate_statistics(&portfolio_performance)
    // let portfolio_stats = calculate_statistics(&portfolio_performance);
    // let (alpha, _beta) = calculate_alpha_beta(&benchmark_g_returns, &portfolio_stats);
    // (alpha,)
    // portfolio_stats
}

fn map_period_deltas_from_summary(
    summary: &TradingSummary,
    interval: u64,
) -> HashMap<u64, Vec<(Asset, f64)>> {
    let mut period_deltas = HashMap::new();
    for pos in summary.positions.iter() {
        let (time, cost, base_gain, close_time, base_cost, gain) = match pos {
            Position::Long(pos) => (
                pos.open_time,
                pos.cost(),
                pos.base_gain(),
                pos.close_time,
                pos.base_cost(),
                pos.gain(),
            ),
            Position::Short(pos) => (
                pos.open_time,
                pos.cost(),
                pos.base_gain(),
                pos.close_time,
                pos.base_cost(),
                pos.gain(),
            ),
        };
        // Open.
        let time = floor_multiple(time, interval);
        let deltas = period_deltas
            .entry(time)
            .or_insert_with(Vec::<(Asset, f64)>::new);
        deltas.push((Asset::Quote, -cost));
        deltas.push((Asset::Base, base_gain));
        // Close.
        let time = floor_multiple(close_time, interval);
        let deltas = period_deltas
            .entry(time)
            .or_insert_with(Vec::<(Asset, f64)>::new);
        deltas.push((Asset::Base, -base_cost));
        deltas.push((Asset::Quote, gain));
    }
    period_deltas
}

fn get_asset_performance(
    summary: &TradingSummary,
    base_prices: &[f64],
    quote_prices: Option<&[f64]>,
    interval: u64,
) -> Vec<HashMap<Asset, f64>> {
    let summary_period_deltas = map_period_deltas_from_summary(summary, interval);

    let start = floor_multiple(summary.start, interval);
    let end = floor_multiple(summary.end, interval);
    let length = ((end - start) / interval) as usize;

    let mut asset_holdings = HashMap::new();
    asset_holdings.insert(Asset::Base, 0.0);
    asset_holdings.insert(Asset::Quote, summary.quote);

    let mut period_asset_performances = Vec::with_capacity(length + 1);

    period_asset_performances.push(get_asset_performances_from_holdings(
        &asset_holdings,
        base_prices[0],
        quote_prices.map(|p| p[0]),
    ));

    for i in 0..length {
        let time = start + i as u64 * interval;
        // Update holdings.
        let deltas = summary_period_deltas.get(&time);
        if let Some(deltas) = deltas {
            for (asset, size) in deltas {
                *asset_holdings.entry(*asset).or_insert(0.0) += size;
            }
        }

        // Update asset performance (mark-to-market portfolio).
        let price_i = i + 1; // Offset the open price.
        period_asset_performances.push(get_asset_performances_from_holdings(
            &asset_holdings,
            base_prices[price_i],
            quote_prices.map(|p| p[price_i]),
        ));
    }

    period_asset_performances
}

fn get_asset_performances_from_holdings(
    asset_holdings: &HashMap<Asset, f64>,
    base_price: f64,
    quote_price: Option<f64>,
) -> HashMap<Asset, f64> {
    // Update asset performance (mark-to-market portfolio).
    let mut asset_performances = HashMap::new();
    for asset in [Asset::Base, Asset::Quote].iter() {
        let entry = asset_performances.entry(*asset).or_insert(0.0);
        *entry = match asset {
            Asset::Base => asset_holdings[asset] * base_price,
            Asset::Quote => asset_holdings[asset] * quote_price.unwrap_or(1.0),
        }
    }
    asset_performances
}

fn calculate_statistics(performance: &[f64]) -> Statistics {
    let mut a_returns = Vec::with_capacity(performance.len() - 1);
    for i in 0..a_returns.capacity() {
        a_returns.push(performance[i + 1] / performance[i] - 1.0);
    }

    let g_returns = a_returns
        .iter()
        .map(|v| (v + 1.0).ln())
        .collect::<Vec<f64>>();
    let annualized_return = 365.0 * mean(&g_returns);

    // Sharpe ratio.
    let sharpe_ratio = if annualized_return.is_nan() || annualized_return == 0.0 {
        0.0
    } else {
        let annualized_volatility = SQRT_365 * std_deviation(&g_returns);
        annualized_return / annualized_volatility
    };

    // Sortino ratio.
    let sortino_ratio = if annualized_return.is_nan() || annualized_return == 0.0 {
        0.0
    } else {
        let neg_g_returns = g_returns
            .iter()
            .cloned()
            .filter(|&v| v < 0.0)
            .collect::<Vec<f64>>();
        let annualized_downside_risk = SQRT_365 * std_deviation(&neg_g_returns);
        // If there are no neg returns, sortino ratio becomes infinite. We will consider it to be
        // 0.0 instead because that is usually a bad run anyway.
        if annualized_downside_risk == 0.0 {
            0.0
        } else {
            annualized_return / annualized_downside_risk
        }
    };

    assert!(sharpe_ratio.is_finite());
    assert!(sortino_ratio.is_finite());

    Statistics {
        // a_returns,
        g_returns,
        // neg_g_returns,
        annualized_return,
        sharpe_ratio,
        sortino_ratio,
    }
}

// fn calculate_alpha_beta(benchmark_g_returns: &[f64], portfolio_stats: &Statistics) -> (f64, f64) {
//     assert!(benchmark_g_returns.len() == portfolio_stats.g_returns.len());

//     // TODO: Inefficient making this copy.
//     let mut combined: Vec<f64> = Vec::with_capacity(benchmark_g_returns.len() * 2);
//     combined.extend(portfolio_stats.g_returns.iter());
//     combined.extend(benchmark_g_returns.iter());

//     let matrix = Array::from_shape_vec((2, benchmark_g_returns.len()), combined)
//         .expect("benchmark and portfolio geometric returns matrix");

//     let covariance_matrix = matrix.cov(0.0).expect("covariance matrix");

//     let beta = covariance_matrix[[0, 1]] / covariance_matrix[[1, 1]];
//     let alpha = portfolio_stats.annualized_return - (beta * 365.0 * mean(&benchmark_g_returns));

//     (alpha, beta)
// }

#[derive(Debug, Serialize)]
pub struct PositionStats {
    #[serde(rename = "type")]
    pub type_: &'static str,
    #[serde(serialize_with = "serialize_timestamp")]
    pub open_time: u64,
    #[serde(serialize_with = "serialize_timestamp")]
    pub close_time: u64,
    pub cost: f64,
    pub gain: f64,
    pub profit: f64,
    #[serde(serialize_with = "serialize_interval")]
    pub duration: u64,
    pub roi: f64,
    pub annualized_roi: f64,
    pub close_reason: CloseReason,
}

impl PositionStats {
    pub fn from_position(pos: &Position) -> Self {
        match pos {
            Position::Long(pos) => {
                let duration = pos.duration();
                let profit = pos.profit();
                let roi = profit / pos.cost();
                Self {
                    type_: "long",
                    open_time: pos.open_time,
                    close_time: pos.close_time,
                    cost: pos.cost(),
                    gain: pos.gain(),
                    profit,
                    duration,
                    roi,
                    annualized_roi: annualized(duration, roi),
                    close_reason: pos.close_reason,
                }
            }
            Position::Short(pos) => {
                let duration = pos.duration();
                let profit = pos.profit();
                let roi = profit / pos.cost();
                Self {
                    type_: "short",
                    open_time: pos.open_time,
                    close_time: pos.close_time,
                    cost: pos.cost(),
                    gain: pos.gain(),
                    profit,
                    duration,
                    roi,
                    annualized_roi: annualized(duration, roi),
                    close_reason: pos.close_reason,
                }
            }
        }
    }
}

#[derive(Debug, Serialize)]
pub struct TradingStats {
    #[serde(serialize_with = "serialize_timestamp")]
    pub start: u64,
    #[serde(serialize_with = "serialize_timestamp")]
    pub end: u64,
    #[serde(serialize_with = "serialize_interval")]
    pub duration: u64,
    pub cost: f64,
    pub gain: f64,
    pub profit: f64,
    pub roi: f64,
    pub annualized_roi: f64,
    pub mean_position_profit: f64,
    #[serde(serialize_with = "serialize_interval")]
    pub mean_position_duration: u64,
    // pub drawdowns: Vec<f64>,
    pub max_drawdown: f64,
    pub mean_drawdown: f64,
    pub num_positions: u32,
    pub num_positions_in_profit: u32,
    pub num_positions_in_loss: u32,
    pub num_stop_losses: u32,
    pub num_take_profits: u32,
    pub sharpe_ratio: f64,
    pub sortino_ratio: f64,

    pub positions: Vec<PositionStats>,
}

impl TradingStats {
    pub fn from_summary(
        summary: &TradingSummary,
        base_prices: &[f64],
        quote_prices: Option<&[f64]>,
        stats_interval: u64,
    ) -> Self {
        let mut quote = summary.quote;
        let mut max_quote = quote;
        let mut profit = 0.0;

        let mut num_positions_in_profit = 0;
        let mut num_positions_in_loss = 0;
        let mut num_stop_losses = 0;
        let mut num_take_profits = 0;

        // let mut drawdowns = Vec::with_capacity(self.positions.len());
        let mut max_drawdown = 0.0;
        let mut total_drawdown = 0.0;

        let mut total_position_duration = 0;

        for pos in summary.positions.iter() {
            let (pos_profit, pos_duration, close_reason) = match pos {
                Position::Long(pos) => (pos.profit(), pos.duration(), pos.close_reason),
                Position::Short(pos) => (pos.profit(), pos.duration(), pos.close_reason),
            };

            profit += pos_profit;
            total_position_duration += pos_duration;

            if pos_profit >= 0.0 {
                num_positions_in_profit += 1;
            } else {
                num_positions_in_loss += 1;
            }

            if close_reason == CloseReason::StopLoss {
                num_stop_losses += 1;
            } else if close_reason == CloseReason::TakeProfit {
                num_take_profits += 1;
            }

            quote += pos_profit;
            max_quote = f64::max(max_quote, quote);
            let drawdown = 1.0 - quote / max_quote;
            // drawdowns.push(drawdown);
            total_drawdown += drawdown;
            max_drawdown = f64::max(max_drawdown, drawdown);
        }

        let (mean_position_profit, mean_position_duration, mean_drawdown) =
            if summary.positions.len() > 0 {
                (
                    profit / summary.positions.len() as f64,
                    total_position_duration / summary.positions.len() as u64,
                    total_drawdown / summary.positions.len() as f64,
                )
            } else {
                (0.0, 0, 0.0)
            };

        let duration = summary.end - summary.start;
        let cost = summary.quote;
        let gain = cost + profit;
        let roi = profit / cost;
        let annualized_roi = annualized(duration, roi);

        let stats = analyse(&summary, &base_prices, quote_prices, stats_interval);

        Self {
            start: summary.start,
            end: summary.end,
            duration,
            cost,
            gain,
            profit,
            roi,
            annualized_roi,
            mean_position_profit,
            mean_position_duration,
            // drawdowns,
            max_drawdown,
            mean_drawdown,
            num_positions: summary.positions.len() as u32,
            num_positions_in_profit,
            num_positions_in_loss,
            num_stop_losses,
            num_take_profits,
            sharpe_ratio: stats.sharpe_ratio,
            sortino_ratio: stats.sortino_ratio,

            positions: summary
                .positions
                .iter()
                .map(PositionStats::from_position)
                .collect(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::trading::LongPosition;

    #[test]
    fn test_sharpe_sortino_nonoptimized_same_as_optimized() {
        let mut summary = TradingSummary::new(0, 10, 1.0);
        summary.positions.push(Position::Long(LongPosition {
            open_time: 2,
            open_quote: 1.0,
            open_size: 2.0,
            open_fee: 0.2,

            close_time: 4,
            close_size: 1.8,
            close_quote: 0.9,
            close_fee: 0.09,
            close_reason: CloseReason::Strategy,
        }));
        summary.positions.push(Position::Long(LongPosition {
            open_time: 6,
            open_quote: 0.81,
            open_size: 1.62,
            open_fee: 0.02,

            close_time: 8,
            close_size: 1.6,
            close_quote: 1.2,
            close_fee: 0.1,
            close_reason: CloseReason::Strategy,
        }));
        let base_prices = vec![1.0; 11];

        let stats = analyse(&summary, &base_prices, None, 1);

        let opt_sharpe = get_sharpe_ratio(&summary, &base_prices, None, 1);
        let opt_sortino = get_sortino_ratio(&summary, &base_prices, None, 1);

        assert_eq!(stats.sharpe_ratio, opt_sharpe);
        assert_eq!(stats.sortino_ratio, opt_sortino);
    }
}

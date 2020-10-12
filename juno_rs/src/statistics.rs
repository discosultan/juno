use crate::{
    math::{floor_multiple, mean, std_deviation},
    trading::{Position, TradingContext},
};
use ndarray::prelude::*;
use ndarray_stats::CorrelationExt;
use std::collections::HashMap;

pub type AnalysisResult = (f64,);

// TODO: Use const fn when `365.0.sqrt()` is supported.
const SQRT_365: f64 = 19.10497317454279908588432590477168560028076171875;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum Asset {
    Base,
    Quote,
}

pub struct Statistics {
    // performance: Vec<f64>,
    // a_returns: Vec<f64>,
    g_returns: Vec<f64>,
    // neg_g_returns: Vec<f64>,

    // total_return: f64,
    annualized_return: f64,
    // annualized_volatility: f64,
    // annualized_downside_risk: f64,
    pub sharpe_ratio: f64,
    pub sortino_ratio: f64,
    // cagr: f64,
}

pub fn analyse(
    base_prices: &[f64],
    quote_prices: Option<&[f64]>,
    _benchmark_g_returns: &[f64],
    summary: &TradingContext,
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
    summary: &TradingContext,
    interval: u64,
) -> HashMap<u64, Vec<(Asset, f64)>> {
    let mut period_deltas = HashMap::new();
    for pos in summary.positions.iter() {
        let (time, cost, base_gain, close_time, base_cost, gain) = match pos {
            Position::Long(pos) => (
                pos.time,
                pos.cost,
                pos.base_gain,
                pos.close_time,
                pos.base_cost,
                pos.gain,
            ),
            Position::Short(pos) => (
                pos.time,
                pos.cost,
                pos.base_gain,
                pos.close_time,
                pos.base_cost,
                pos.gain,
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
    summary: &TradingContext,
    base_prices: &[f64],
    quote_prices: Option<&[f64]>,
    interval: u64,
) -> Vec<HashMap<Asset, f64>> {
    let period_deltas = map_period_deltas_from_summary(summary, interval);

    let start = floor_multiple(summary.start, interval);
    let end = floor_multiple(summary.end, interval);
    let length = ((end - start) / interval) as usize;

    let mut asset_holdings = HashMap::new();
    asset_holdings.insert(Asset::Base, 0.0);
    asset_holdings.insert(Asset::Quote, summary.quote);

    let mut period_asset_performances = Vec::with_capacity(length);

    for i in 0..length {
        let time = start + i as u64 * interval;
        // Update holdings.
        let deltas = period_deltas.get(&time);
        if let Some(deltas) = deltas {
            for (asset, size) in deltas {
                *asset_holdings.entry(*asset).or_insert(0.0) += size;
            }
        }

        // Update asset performance (mark-to-market portfolio).
        let mut asset_performances = HashMap::new();
        for asset in [Asset::Base, Asset::Quote].iter() {
            let entry = asset_performances.entry(*asset).or_insert(0.0);
            *entry = match asset {
                Asset::Base => asset_holdings[asset] * base_prices[i],
                Asset::Quote => match quote_prices {
                    Some(prices) => asset_holdings[asset] * prices[i],
                    None => asset_holdings[asset],
                },
            }
        }
        period_asset_performances.push(asset_performances);
    }

    period_asset_performances
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
    let annualized_volatility = SQRT_365 * std_deviation(&g_returns);
    let sharpe_ratio = if annualized_volatility != 0.0 {
        annualized_return / annualized_volatility
    } else {
        0.0
    };

    // Sortino ratio.
    let neg_g_returns = g_returns
        .iter()
        .cloned()
        .filter(|&v| v < 0.0)
        .collect::<Vec<f64>>();
    let annualized_downside_risk = SQRT_365 * std_deviation(&neg_g_returns);
    let sortino_ratio = annualized_return / annualized_downside_risk;

    Statistics {
        // a_returns,
        g_returns,
        // neg_g_returns,
        annualized_return,
        sharpe_ratio,
        sortino_ratio,
    }
}

fn calculate_alpha_beta(benchmark_g_returns: &[f64], portfolio_stats: &Statistics) -> (f64, f64) {
    assert!(benchmark_g_returns.len() == portfolio_stats.g_returns.len());

    // TODO: Inefficient making this copy.
    let mut combined: Vec<f64> = Vec::with_capacity(benchmark_g_returns.len() * 2);
    combined.extend(portfolio_stats.g_returns.iter());
    combined.extend(benchmark_g_returns.iter());

    let matrix = Array::from_shape_vec((2, benchmark_g_returns.len()), combined)
        .expect("benchmark and portfolio geometric returns matrix");

    let covariance_matrix = matrix.cov(0.0).expect("covariance matrix");

    let beta = covariance_matrix[[0, 1]] / covariance_matrix[[1, 1]];
    let alpha = portfolio_stats.annualized_return - (beta * 365.0 * mean(&benchmark_g_returns));

    (alpha, beta)
}

pub fn get_sharpe_ratio(
    summary: &TradingContext,
    base_prices: &[f64],
    quote_prices: Option<&[f64]>,
    interval: u64,
) -> f64 {
    let period_deltas = map_period_deltas_from_summary(summary, interval);

    let start = floor_multiple(summary.start, interval);
    let end = floor_multiple(summary.end, interval);
    let length = ((end - start) / interval) as usize;

    let mut base_holding = 0.0;
    let mut quote_holding = summary.quote;

    let mut prev_performance = match quote_prices {
        Some(quote_prices) => quote_holding * quote_prices[0], // TODO: Use candle open price here?
        None => quote_holding,
    };

    let mut g_returns = Vec::with_capacity(length);
    let mut sum_g_returns = 0.0;

    for (i, time) in (start..end).step_by(interval as usize).enumerate() {
        let deltas = period_deltas.get(&time);
        if let Some(deltas) = deltas {
            for (asset, size) in deltas {
                match asset {
                    Asset::Base => base_holding += size,
                    Asset::Quote => quote_holding += size,
                }
            }
        }
        let performance = base_holding * base_prices[i]
            + match quote_prices {
                Some(quote_prices) => quote_holding * quote_prices[i],
                None => quote_holding,
            };

        let a_return = performance / prev_performance - 1.0;

        let g_return = (a_return + 1.0).ln();
        g_returns.push(g_return);
        sum_g_returns += g_return;

        prev_performance = performance;
    }

    let mean_g_returns = sum_g_returns / length as f64;
    let annualized_return = 365.0 * mean_g_returns;

    let sharpe_ratio = if annualized_return.is_nan() || annualized_return == 0.0 {
        0.0
    } else {
        let variance = g_returns
            .iter()
            .map(|value| {
                let diff = mean_g_returns - value;
                diff * diff
            })
            .sum::<f64>()
            / length as f64;
        let std_dev = variance.sqrt();
        let annualized_volatility = SQRT_365 * std_dev;
        annualized_return / annualized_volatility
    };

    sharpe_ratio
}

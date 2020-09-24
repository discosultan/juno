use crate::{
    common::Candle,
    math::{floor_multiple, mean, std_deviation},
    trading::{Position, TradingSummary},
};
use ndarray::prelude::*;
use ndarray_stats::CorrelationExt;
use std::{cmp::max, collections::HashMap, error::Error};

pub type AnalysisResult = (f64,);

const DAY_MS: u64 = 86_400_000;

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
    quote_fiat_prices: &[f64],
    base_fiat_prices: &[f64],
    _benchmark_g_returns: &[f64],
    summary: &TradingSummary,
) -> Statistics {
    let interval = max(DAY_MS, summary.interval);
    let trades = get_trades_from_summary(summary, interval);
    let asset_performance = get_asset_performance(
        summary,
        quote_fiat_prices,
        base_fiat_prices,
        &trades,
        interval,
    );
    let portfolio_performance = asset_performance
        .iter()
        .map(|d| d.values().sum())
        .collect::<Vec<f64>>();
    let portfolio_stats = calculate_statistics(&portfolio_performance);
    // let (alpha, _beta) = calculate_alpha_beta(&benchmark_g_returns, &portfolio_stats);
    // (alpha,)
    portfolio_stats
}

fn get_trades_from_summary(
    summary: &TradingSummary,
    interval: u64,
) -> HashMap<u64, Vec<(Asset, f64)>> {
    let mut trades = HashMap::new();
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
        let day_trades = trades.entry(time).or_insert_with(Vec::<(Asset, f64)>::new);
        day_trades.push((Asset::Quote, -cost));
        day_trades.push((Asset::Base, base_gain));
        // Close.
        let time = floor_multiple(close_time, interval);
        let day_trades = trades.entry(time).or_insert_with(Vec::<(Asset, f64)>::new);
        day_trades.push((Asset::Base, -base_cost));
        day_trades.push((Asset::Quote, gain));
    }
    trades
}

fn get_asset_performance(
    summary: &TradingSummary,
    quote_fiat_daily: &[f64],
    base_fiat_daily: &[f64],
    trades: &HashMap<u64, Vec<(Asset, f64)>>,
    interval: u64,
) -> Vec<HashMap<Asset, f64>> {
    let start_day = floor_multiple(summary.start, interval);
    let length = quote_fiat_daily.len() as u64;

    let mut asset_holdings = HashMap::new();
    asset_holdings.insert(Asset::Base, 0.0);
    asset_holdings.insert(Asset::Quote, summary.cost);

    let mut asset_performance = Vec::with_capacity(length as usize);

    for i in 0..length {
        let time_day = start_day + i * interval;
        // Update holdings.
        let day_trades = trades.get(&time_day);
        if let Some(day_trades) = day_trades {
            for (asset, size) in day_trades {
                *asset_holdings.entry(*asset).or_insert(0.0) += size;
            }
        }

        // Update asset performance (mark-to-market portfolio).
        let mut asset_performance_day = HashMap::new();
        for asset in [Asset::Base, Asset::Quote].iter() {
            // TODO: improve this shit.
            let asset_fiat_value = if *asset == Asset::Base {
                base_fiat_daily[i as usize]
            } else {
                quote_fiat_daily[i as usize]
            };
            *asset_performance_day.entry(*asset).or_insert(0.0) =
                asset_holdings[asset] * asset_fiat_value;
        }
        asset_performance.push(asset_performance_day);
    }

    asset_performance
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
    let annualized_return = 365.0_f64 * mean(&g_returns).expect("g_returns to not be empty");
    // TODO: Set this as a const. However, `sqrt()` is not supported as a const fn as of now.
    let sqrt_365 = 365.0_f64.sqrt();

    // Sharpe ratio.
    let annualized_volatility =
        sqrt_365 * std_deviation(&g_returns).expect("g_returns to not be empty");
    let sharpe_ratio = annualized_return / annualized_volatility;

    // Sortino ratio.
    let neg_g_returns = g_returns
        .iter()
        .cloned()
        .filter(|&v| v < 0.0)
        .collect::<Vec<f64>>();
    let annualized_downside_risk =
        sqrt_365 * std_deviation(&neg_g_returns).expect("neg_g_returns to not be empty");
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

    let covariance_matrix = matrix.cov(1.0).expect("covariance matrix");

    let beta = covariance_matrix[[0, 1]] / covariance_matrix[[1, 1]];
    let alpha = portfolio_stats.annualized_return
        - (beta * 365.0 * mean(&benchmark_g_returns).expect("benchmark_g_returns to not be empty"));

    (alpha, beta)
}

pub fn calculate_sharpe_ratio(
    summary: &TradingSummary,
    candles: &[Candle],
    interval: u64,
) -> Result<f64, Box<dyn Error>> {
    let performance = get_portfolio_performance(summary, candles, interval);
    let mut a_returns = Vec::with_capacity(performance.len() - 1);
    for i in 0..a_returns.capacity() {
        a_returns.push(performance[i + 1] / performance[i] - 1.0);
    }

    let g_returns = a_returns
        .iter()
        .map(|v| (v + 1.0).ln())
        .collect::<Vec<f64>>();
    let annualized_return = 365.0_f64 * mean(&g_returns).ok_or("g_returns empty")?;
    // TODO: Set this as a const. However, `sqrt()` is not supported as a const fn as of now.
    let sqrt_365 = 365.0_f64.sqrt();

    let annualized_volatility = sqrt_365 * std_deviation(&g_returns).ok_or("g_returns empty")?;

    // Sharpe ratio.
    if annualized_return.is_nan() {
        Ok(0.0)
    } else {
        Ok(annualized_return / annualized_volatility)
    }
}

fn get_portfolio_performance(
    summary: &TradingSummary,
    candles: &[Candle],
    interval: u64,
) -> Vec<f64> {
    let deltas = get_trades_from_summary(summary, interval);

    let start_day = floor_multiple(summary.start, interval);
    let end_day = floor_multiple(summary.end, interval);
    let length = (end_day - start_day) / interval;

    let mut running = summary.cost;
    let mut performance = Vec::with_capacity(length as usize);
    performance.push(running);

    for i in 0..length {
        let time_day = start_day + i * interval;
        // Update holdings.
        let day_deltas = deltas.get(&time_day);
        if let Some(day_trades) = day_deltas {
            for (asset, size) in day_trades {
                if *asset == Asset::Quote {
                    running += size;
                } else {
                    running += size * candles[i as usize].close;
                }
            }
        }
        performance.push(running);
    }

    performance
}

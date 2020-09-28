use crate::{
    common::Candle,
    math::{floor_multiple, mean, std_deviation},
    trading::{Position, TradingContext},
};
use lazy_static::lazy_static;
use ndarray::prelude::*;
use ndarray_stats::CorrelationExt;
use std::{collections::HashMap, error::Error};

pub type AnalysisResult = (f64,);

const DAY_MS: u64 = 86_400_000;

lazy_static! {
    static ref SQRT_365: f64 = 365.0_f64.sqrt();
}

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
    summary: &TradingContext,
    interval: u64,
) -> Statistics {
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
    calculate_statistics(&portfolio_performance)
    // let portfolio_stats = calculate_statistics(&portfolio_performance);
    // let (alpha, _beta) = calculate_alpha_beta(&benchmark_g_returns, &portfolio_stats);
    // (alpha,)
    // portfolio_stats
}

fn get_trades_from_summary(
    summary: &TradingContext,
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
        let deltas = trades.entry(time).or_insert_with(Vec::<(Asset, f64)>::new);
        deltas.push((Asset::Quote, -cost));
        deltas.push((Asset::Base, base_gain));
        // Close.
        let time = floor_multiple(close_time, interval);
        let deltas = trades.entry(time).or_insert_with(Vec::<(Asset, f64)>::new);
        deltas.push((Asset::Base, -base_cost));
        deltas.push((Asset::Quote, gain));
    }
    trades
}

fn get_asset_performance(
    summary: &TradingContext,
    quote_fiat_daily: &[f64],
    base_fiat_daily: &[f64],
    trades: &HashMap<u64, Vec<(Asset, f64)>>,
    interval: u64,
) -> Vec<HashMap<Asset, f64>> {
    let start_day = floor_multiple(summary.start, interval);
    let length = quote_fiat_daily.len() as u64;

    let mut asset_holdings = HashMap::new();
    asset_holdings.insert(Asset::Base, 0.0);
    asset_holdings.insert(Asset::Quote, summary.quote);

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
    let annualized_return = 365.0 * mean(&g_returns);

    // Sharpe ratio.
    let annualized_volatility = *SQRT_365 * std_deviation(&g_returns);
    let sharpe_ratio = annualized_return / annualized_volatility;

    // Sortino ratio.
    let neg_g_returns = g_returns
        .iter()
        .cloned()
        .filter(|&v| v < 0.0)
        .collect::<Vec<f64>>();
    let annualized_downside_risk = *SQRT_365 * std_deviation(&neg_g_returns);
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
    let alpha = portfolio_stats.annualized_return - (beta * 365.0 * mean(&benchmark_g_returns));

    (alpha, beta)
}

pub fn get_sharpe_ratio(
    summary: &TradingContext,
    candles: &[Candle],
    interval: u64,
) -> Result<f64, Box<dyn Error>> {
    let deltas = get_trades_from_summary(summary, interval);

    let start = floor_multiple(summary.start, interval);
    let end = floor_multiple(summary.end, interval);
    let length = ((end - start) / interval) as usize;

    let mut prev_performance = summary.quote;
    let mut performance = summary.quote;

    let mut g_returns = Vec::with_capacity(length);
    let mut sum_g_returns = 0.0;

    for (time, candle) in (start..end).step_by(interval as usize).zip(candles) {
        let deltas = deltas.get(&time);
        if let Some(deltas) = deltas {
            for (asset, size) in deltas {
                match asset {
                    Asset::Quote => performance += size,
                    Asset::Base => performance += size * candle.close,
                }
            }
        }

        let a_return = performance / prev_performance - 1.0;

        let g_return = (a_return + 1.0).ln();
        g_returns.push(g_return);
        sum_g_returns += g_return;

        prev_performance = performance;
    }

    let mean_g_returns = sum_g_returns / length as f64;

    let annualized_return = 365.0 * mean_g_returns;
    if annualized_return.is_nan() || annualized_return == 0.0 {
        Ok(0.0)
    } else {
        let variance =  g_returns
            .iter()
            .map(|value| {
                let diff = mean_g_returns - value;
                diff * diff
            })
            .sum::<f64>() / length as f64;
        let annualized_volatility = *SQRT_365 * variance.sqrt();
        // Sharpe ratio.
        Ok(annualized_return / annualized_volatility)
    }

    // let performance = get_portfolio_performance(summary, candles, interval);
    // let mut a_returns = Vec::with_capacity(performance.len() - 1);
    // for i in 0..a_returns.capacity() {
    //     a_returns.push(performance[i + 1] / performance[i] - 1.0);
    // }

    // let g_returns = a_returns
    //     .iter()
    //     .map(|v| (v + 1.0).ln())
    //     .collect::<Vec<f64>>();
    // let annualized_return = 365.0 * mean(&g_returns);

    // if annualized_return.is_nan() || annualized_return == 0.0 {
    //     Ok(0.0)
    // } else {
    //     let annualized_volatility = *SQRT_365 * std_deviation(&g_returns);
    //     // Sharpe ratio.
    //     Ok(annualized_return / annualized_volatility)
    // }
}

// fn get_portfolio_performance(
//     summary: &TradingSummary,
//     candles: &[Candle],
//     interval: u64,
// ) -> Vec<f64> {
//     let deltas = get_trades_from_summary(summary, interval);

//     let start = floor_multiple(summary.start, interval);
//     let end = floor_multiple(summary.end, interval);
//     let length = ((end - start) / interval) as usize;

//     let mut running = summary.cost;
//     let mut performance = Vec::with_capacity(length + 1);
//     performance.push(running);

//     for (time, candle) in (start..end).step_by(interval as usize).zip(candles) {
//         // Update holdings.
//         let deltas = deltas.get(&time);
//         if let Some(deltas) = deltas {
//             for (asset, size) in deltas {
//                 match asset {
//                     Asset::Quote => running += size,
//                     Asset::Base => running += size * candle.close,
//                 }
//             }
//         }
//         performance.push(running);
//     }

//     performance
// }

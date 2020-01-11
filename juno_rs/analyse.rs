use std::collections::HashMap;
use ndarray::prelude::*;
use ndarray_stats::CorrelationExt;
use crate::{
    Candle,
    math::{floor_multiple, mean},
    trading::TradingSummary
};

pub type AnalysisResult = (f64, );

const DAY_MS: u64 = 86_400_000;

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
enum Asset
{
    Base,
    Quote,
}

struct Statistics {
    // performance: Vec<f64>,
    // a_returns: Vec<f64>,
    g_returns: Vec<f64>,
    // neg_g_returns: Vec<f64>,

    // total_return: f64,
    annualized_return: f64,
    // annualized_volatility: f64,
    // annualized_downside_risk: f64,
    // sharpe_ratio: f64,
    // sortino_ratio: f64,
    // cagr: f64,
}

pub fn analyse(
    quote_fiat_daily: &[Candle],
    base_fiat_daily: &[f64],
    benchmark_g_returns: &[f64],
    summary: &TradingSummary,
) -> AnalysisResult {
    let trades = get_trades_from_summary(summary);
    let asset_performance = get_asset_performance(summary, quote_fiat_daily, base_fiat_daily, &trades);
    let portfolio_performance = asset_performance
        .iter()
        .map(|d| d.values().sum())
        .collect::<Vec<f64>>();
    println!("benchmark {:?}", quote_fiat_daily.iter().map(|c| c.close).collect::<Vec<f64>>());
    println!("portfolio {:?}", portfolio_performance);
    let portfolio_stats = calculate_statistics(&portfolio_performance);
    let (alpha, _beta) = calculate_alpha_beta(&benchmark_g_returns, portfolio_stats);
    (alpha, )
}

fn get_trades_from_summary(summary: &TradingSummary) -> HashMap<u64, Vec<(Asset, f64)>> {
    let mut trades = HashMap::new();
    for pos in &summary.positions {
        // Open.
        let time = floor_multiple(pos.time, DAY_MS);
        let day_trades = trades
            .entry(time)
            .or_insert(Vec::<(Asset, f64)>::new());
        day_trades.push((Asset::Quote, -pos.cost));
        day_trades.push((Asset::Base, pos.base_gain));
        // Close.
        let time = floor_multiple(pos.close_time, DAY_MS);
        let day_trades = trades
            .entry(time)
            .or_insert(Vec::<(Asset, f64)>::new());
        day_trades.push((Asset::Base, -pos.base_cost));
        day_trades.push((Asset::Quote, pos.gain));
    }
    trades
}

fn get_asset_performance(
    summary: &TradingSummary,
    quote_fiat_daily: &[Candle],
    base_fiat_daily: &[f64],
    trades: &HashMap<u64, Vec<(Asset, f64)>>,
) -> Vec<HashMap<Asset, f64>> {
    let start_day = floor_multiple(summary.start, DAY_MS);
    let length = quote_fiat_daily.len() as u64;

    let mut asset_holdings = HashMap::new();
    asset_holdings.insert(Asset::Base, 0.0);
    asset_holdings.insert(Asset::Quote, summary.cost);

    let mut asset_performance = Vec::with_capacity(length as usize);

    for i in 0..length {
        let time_day = start_day + i * DAY_MS;
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
                quote_fiat_daily[i as usize].close
            };
            *asset_performance_day
                .entry(*asset)
                .or_insert(0.0) = asset_holdings[asset] * asset_fiat_value;
        }
        asset_performance.push(asset_performance_day);
    }

    asset_performance
}

fn calculate_statistics(performance: &[f64]) -> Statistics {
    let returns_len = performance.len() - 1;

    let mut a_returns = Vec::with_capacity(returns_len);
    for i in 0..returns_len {
        a_returns.push(performance[i + 1] / performance[i] - 1.0);
    }

    let mut g_returns = Vec::with_capacity(returns_len);
    for i in 0..returns_len {
        g_returns.push((a_returns[i] + 1.0).ln());
    }

    // let mut neg_g_returns = Vec::new();
    // for g_return in g_returns.into_iter() {
    //     if g_return < 0.0 {
    //         neg_g_returns.push(g_return);
    //     }
    // }

    let annualized_return = 365.0 * mean(&g_returns);

    Statistics {
        // a_returns,
        g_returns,
        // neg_g_returns,

        annualized_return
    }
}

// TODO: hax! portfolio stats shouldn't be mutable.
fn calculate_alpha_beta(benchmark_g_returns: &[f64], mut portfolio_stats: Statistics) -> (f64, f64) {
    portfolio_stats.g_returns.extend(benchmark_g_returns.iter());

    let matrix = Array::from_shape_vec(
        (2, benchmark_g_returns.len()),
        portfolio_stats.g_returns
    ).unwrap();

    let covariance_matrix = matrix.cov(1.).unwrap();

    let beta = covariance_matrix[[0, 1]] / covariance_matrix[[1, 1]];
    let alpha = portfolio_stats.annualized_return - (beta * 365.0 * mean(&benchmark_g_returns));

    (alpha, beta)
}

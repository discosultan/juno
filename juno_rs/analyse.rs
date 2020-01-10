use std::collections::HashMap;
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
    let portfolio_stats = calculate_statistics(&portfolio_performance);
    let (alpha, beta) = calculate_alpha_beta(&benchmark_g_returns, &portfolio_stats);
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
    let end_day = floor_multiple(summary.end, DAY_MS);
    let length = (end_day - start_day) / summary.interval;

    let mut asset_holdings = HashMap::new();
    asset_holdings.insert(Asset::Quote, summary.cost);

    let mut asset_performance = Vec::with_capacity(length as usize);

    // let step_size = summary.interval as usize;
    for i in 0..length {
        let time_day = start_day + i * summary.interval;
    // for time_day in (start_day..end_day).step_by(step_size) {
        // Update holdings.
        let day_trades = trades.get(&time_day);
        if let Some(day_trades) = day_trades {
            for (asset, size) in day_trades {
                *asset_holdings.entry(*asset).or_insert(0.0) += size;
            }
        }

        // Update asset performance (mark-to-market portfolio).
        let mut asset_performance_day = HashMap::new();
        //  asset_performance
        //     .entry(time_day)
        //     .or_insert(HashMap::new());
            // .or_insert_with(|| {
            //     let mut hash_map = HashMap::<Asset, f64>::new();
            //     hash_map.insert(Asset::Quote, 0.0);
            //     hash_map.insert(Asset::Base, 0.0);
            //     hash_map
            // });
        for asset in [Asset::Base, Asset::Quote].iter() {
            // TODO: improve this shit.
            let asset_fiat_value = if *asset == Asset::Base {
                base_fiat_daily[(time_day / summary.interval) as usize]
            } else {
                quote_fiat_daily[(time_day / summary.interval) as usize].close
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
        a_returns[i] = performance[i + 1] / performance[i];
    }

    let mut g_returns = Vec::with_capacity(returns_len);
    for i in 0..returns_len {
        g_returns[i] = (a_returns[i] + 1.0).ln();
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

fn calculate_alpha_beta(benchmark_g_returns: &[f64], portfolio_stats: &Statistics) -> (f64, f64) {
    // covariance_matrix = pd.concat(
    //     [portfolio_stats.g_returns, benchmark_stats.g_returns], axis=1
    // ).dropna().cov()
    // let beta = covariance_matrix.iloc[0].iloc[1] / covariance_matrix.iloc[1].iloc[1]
    // let alpha = portfolio_stats.annualized_return - (beta * 365 * benchmark_stats.g_returns.mean())

    // (alpha, beta)

    (0.0, 0.0)
}

use crate::{
    common::Candle,
    itertools::IteratorExt,
    math::{floor_multiple, mean, std_deviation},
    trading::{Position, TradingSummary},
};
use lazy_static::lazy_static;
use ndarray::prelude::*;
use ndarray_stats::CorrelationExt;
use std::{cell::Cell, cmp::max, collections::HashMap};

pub type AnalysisResult = (f64,);

const DAY_MS: u64 = 86_400_000;

lazy_static! {
    static ref SQRT_365: f64 = 365.0;
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
    calculate_statistics(&portfolio_performance)
    // let portfolio_stats = calculate_statistics(&portfolio_performance);
    // let (alpha, _beta) = calculate_alpha_beta(&benchmark_g_returns, &portfolio_stats);
    // (alpha,)
    // portfolio_stats
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
    let annualized_return = 365.0_f64 * mean(&g_returns);

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

// Not Sync!
pub struct StatisticsContext {
    candles_filled: Vec<Candle>,
    start: u64,
    interval: u64,

    asset_deltas: Cell<Vec<HashMap<Asset, f64>>>,
    performance: Cell<Vec<f64>>,
    a_returns: Cell<Vec<f64>>,
    g_returns: Cell<Vec<f64>>,
}

impl StatisticsContext {
    pub fn new(interval: u64, start: u64, end: u64, candles: &[Candle]) -> Self {
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
            }
            candles_filled.push(*candle);
            prev_candle = Some(candle);
            current += interval;
        }
        assert_eq!(candles_filled.len(), length);

        Self {
            candles_filled,
            start,
            interval,
            asset_deltas: Cell::new(vec![HashMap::new(); 2]),
            performance: Cell::new(Vec::with_capacity(length)),
            a_returns: Cell::new(Vec::with_capacity(length - 1)),
            g_returns: Cell::new(Vec::with_capacity(length - 1)),
        }
    }

    pub fn get_sharpe_ratio(&self, summary: &TradingSummary) -> f64 {
        self.populate_asset_deltas(summary);
        self.populate_performance(summary);

        let performance = self.performance.get_mut();
        let a_returns = self.a_returns.get_mut();
        let g_returns = self.g_returns.get_mut();

        a_returns.extend(performance.iter().pairwise().map(|(a, b)| b / a - 1.0));
        g_returns.extend(a_returns.iter().map(|v| (v + 1.0).ln()));

        let annualized_return = 365.0 * mean(g_returns);
        let sharpe_ratio = if annualized_return.is_nan() || annualized_return == 0.0 {
            0.0
        } else {
            let annualized_volatility = *SQRT_365 * std_deviation(g_returns);
            annualized_return / annualized_volatility
        };

        self.clear();

        sharpe_ratio
    }

    fn len(&self) -> usize {
        self.candles_filled.len()
    }

    fn clear(&mut self) {
        self.asset_deltas.get_mut().iter_mut().for_each(|d| d.clear());
        self.performance.get_mut().clear();
        self.a_returns.get_mut().clear();
        self.g_returns.get_mut().clear();
    }

    fn populate_asset_deltas(&mut self, summary: &TradingSummary) {
        let asset_deltas = self.asset_deltas.get_mut();

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
            let i = (floor_multiple(time, self.interval) - self.start) / self.interval;
            let period_deltas = &mut asset_deltas[i as usize];
            *period_deltas.entry(Asset::Quote).or_default() -= cost;
            *period_deltas.entry(Asset::Base).or_default() += base_gain;

            // Close.
            let i = (floor_multiple(close_time, self.interval) - self.start) / self.interval;
            let period_deltas = &mut asset_deltas[i as usize];
            *period_deltas.entry(Asset::Base).or_default() -= base_cost;
            *period_deltas.entry(Asset::Quote).or_default() += gain;
        }
    }

    fn populate_performance(&mut self, summary: &TradingSummary) {
        let asset_deltas = self.asset_deltas.get_mut();
        let performance = self.performance.get_mut();

        let mut running = summary.cost;
        performance.push(running);

        for i in 0..self.len() {
            // Update holdings.
            let period_deltas = &asset_deltas[i];
            if period_deltas.len() > 0 {
                for (asset, size) in period_deltas {
                    match asset {
                        Asset::Quote => running += size,
                        Asset::Base => running += size * self.candles_filled[i].close,
                    }
                }
            }
            performance.push(running);
        }
    }
}

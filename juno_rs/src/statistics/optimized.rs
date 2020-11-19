use super::{map_period_deltas_from_summary, Asset, SQRT_365};
use crate::{math::floor_multiple, trading::TradingSummary};

// Prices have one extra price in the beginning which is the opening price of the first candle.

pub fn get_sharpe_ratio(
    summary: &TradingSummary,
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
        Some(quote_prices) => quote_holding * quote_prices[0], // 0 is open price.
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
        let price_i = i + 1; // Offset the open price.
        let performance = base_holding * base_prices[price_i]
            + match quote_prices {
                Some(quote_prices) => quote_holding * quote_prices[price_i],
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

    debug_assert!(sharpe_ratio.is_finite());
    sharpe_ratio
}

pub fn get_sortino_ratio(
    summary: &TradingSummary,
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
        Some(quote_prices) => quote_holding * quote_prices[0], // 0 is open price.
        None => quote_holding,
    };

    let mut g_returns = Vec::with_capacity(length);
    let mut sum_g_returns = 0.0;
    let mut len_neg_g_returns = 0;
    let mut sum_neg_g_returns = 0.0;

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
        let price_i = i + 1; // Offset the open price.
        let performance = base_holding * base_prices[price_i]
            + match quote_prices {
                Some(quote_prices) => quote_holding * quote_prices[price_i],
                None => quote_holding,
            };

        let a_return = performance / prev_performance - 1.0;

        let g_return = (a_return + 1.0).ln();
        g_returns.push(g_return);
        sum_g_returns += g_return;
        if g_return < 0.0 {
            sum_neg_g_returns += g_return;
            len_neg_g_returns += 1;
        }

        prev_performance = performance;
    }

    let mean_neg_g_returns = sum_neg_g_returns / len_neg_g_returns as f64;
    let mean_g_returns = sum_g_returns / length as f64;
    let annualized_return = 365.0 * mean_g_returns;

    let sortino_ratio = if annualized_return.is_nan() || annualized_return == 0.0 {
        0.0
    } else {
        let variance = g_returns
            .iter()
            .cloned()
            .filter(|&v| v < 0.0)
            .map(|value| {
                let diff = mean_neg_g_returns - value;
                diff * diff
            })
            .sum::<f64>()
            / len_neg_g_returns as f64;
        let std_dev = variance.sqrt();
        let annualized_downside_risk = SQRT_365 * std_dev;
        if annualized_downside_risk == 0.0 {
            0.0
        } else {
            annualized_return / annualized_downside_risk
        }
    };

    debug_assert!(sortino_ratio.is_finite());
    sortino_ratio
}

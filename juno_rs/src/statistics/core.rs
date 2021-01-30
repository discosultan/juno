use super::PositionStatistics;
use crate::{
    math::annualized,
    time::{serialize_interval, serialize_timestamp},
    trading::{CloseReason, Position, TradingSummary},
};
use serde::Serialize;

#[derive(Serialize)]
pub struct CoreStatistics {
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
    pub return_over_max_drawdown: f64,
    pub num_positions: u32,
    pub num_positions_in_profit: u32,
    pub num_positions_in_loss: u32,
    pub num_stop_losses: u32,
    pub num_take_profits: u32,

    pub positions: Vec<PositionStatistics>,
}

impl CoreStatistics {
    pub fn compose(summary: &TradingSummary) -> Self {
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
        let return_over_max_drawdown = if max_drawdown == 0.0 {
            0.0
        } else {
            roi / max_drawdown
        };

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
            return_over_max_drawdown,
            // drawdowns,
            max_drawdown,
            mean_drawdown,
            num_positions: summary.positions.len() as u32,
            num_positions_in_profit,
            num_positions_in_loss,
            num_stop_losses,
            num_take_profits,

            positions: summary
                .positions
                .iter()
                .map(PositionStatistics::from_position)
                .collect(),
        }
    }
}

pub fn get_profit(summary: &TradingSummary) -> f64 {
    summary
        .positions
        .iter()
        .map(|pos| match pos {
            Position::Long(pos) => pos.profit(),
            Position::Short(pos) => pos.profit(),
        })
        .sum()
}

pub fn get_return_over_max_drawdown(summary: &TradingSummary) -> f64 {
    let mut quote = summary.quote;
    let mut max_quote = quote;
    let mut profit = 0.0;
    let mut max_drawdown = 0.0;

    for pos in summary.positions.iter() {
        let pos_profit = match pos {
            Position::Long(pos) => pos.profit(),
            Position::Short(pos) => pos.profit(),
        };

        profit += pos_profit;
        quote += pos_profit;
        max_quote = f64::max(max_quote, quote);
        let drawdown = 1.0 - quote / max_quote;
        max_drawdown = f64::max(max_drawdown, drawdown);
    }

    let roi = profit / summary.quote;

    return if max_drawdown == 0.0 {
        0.0
    } else {
        roi / max_drawdown
    };
}

#[cfg(test)]
mod tests {
    use super::super::test_utils;
    use super::*;

    #[test]
    fn test_nonoptimized_stats_same_as_optimized() {
        let summary = test_utils::get_populated_trading_summary();

        let stats = CoreStatistics::compose(&summary);

        let opt_profit = get_profit(&summary);
        let opt_return_over_max_drawdown = get_return_over_max_drawdown(&summary);

        assert_eq!(stats.profit, opt_profit);
        assert_eq!(stats.return_over_max_drawdown, opt_return_over_max_drawdown);
    }
}

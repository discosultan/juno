mod core;
mod extended;
pub use self::core::*;
pub use extended::*;

use crate::{
    math::annualized,
    time::{serialize_interval, serialize_timestamp},
    trading::{CloseReason, Position, TradingSummary},
};
use serde::Serialize;

// TODO: Use const fn when `365.0.sqrt()` is supported.
pub(crate) const SQRT_365: f64 = 19.10497317454279908588432590477168560028076171875;

#[derive(Debug, Serialize)]
pub struct PositionStatistics {
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

impl PositionStatistics {
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

#[derive(Serialize)]
pub struct Statistics {
    pub core: CoreStatistics,
    pub extended: ExtendedStatistics,
}

impl Statistics {
    pub fn compose(
        summary: &TradingSummary,
        base_prices: &[f64],
        quote_prices: Option<&[f64]>,
        stats_interval: u64,
    ) -> Self {
        Self {
            core: CoreStatistics::compose(summary),
            extended: ExtendedStatistics::compose(
                &summary,
                &base_prices,
                quote_prices,
                stats_interval,
            ),
        }
    }
}

#[cfg(test)]
mod test_utils {
    use crate::trading::{CloseReason, LongPosition, Position, TradingSummary};

    pub fn get_populated_trading_summary() -> TradingSummary {
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
        summary
    }
}

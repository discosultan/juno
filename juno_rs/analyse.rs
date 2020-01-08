use std::collections::HashMap;
use crate::Candle;
use crate::trading::TradingSummary;

pub type AnalysisResult = (f64, );

const DAY_MS: u64 = 86_400_000;

pub fn analyse(
    quote_fiat_daily: &[Candle],
    base_fiat_daily: &[f64],
    benchmark_g_returns: &[f64],
    summary: &TradingSummary,
) -> AnalysisResult {
    // let mut trades = HashMap::new();
    for pos in &summary.positions {
        // let time = 
    }

    (0.0, )
}

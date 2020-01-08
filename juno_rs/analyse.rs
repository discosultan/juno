use crate::Candle;
use crate::trading::TradingSummary;

pub type AnalysisResult = (f64, );

pub fn analyse(
    quote_fiat_daily: &[Candle],
    base_fiat_daily: &[f64],
    benchmark_g_returns: &[f64],
    summary: &TradingSummary,
) -> AnalysisResult {
    (0.0, )
}

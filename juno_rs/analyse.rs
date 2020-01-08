use crate::Candle;

pub type AnalysisResult = (f64, );

pub fn analyse(
    benchmark_g_returns: &[Candle],
    base_fiat_candles: &[Candle],
    portfolio_candles: &[f64],
) -> AnalysisResult {
    (0.0, )
}



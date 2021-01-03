use crate::Candle;

pub fn candles_to_prices(candles: &[Candle], multipliers: Option<&[f64]>) -> Vec<f64> {
    let mut prices = Vec::with_capacity(candles.len() + 1);
    prices.push(candles[0].open * multipliers.map_or(1.0, |m| m[0]));
    for i in 0..candles.len() {
        let multiplier_i = i + 1; // Has to be offset by 1.
        prices.push(candles[i].close * multipliers.map_or(1.0, |m| m[multiplier_i]));
    }
    prices
}

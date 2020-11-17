use crate::{math::floor_multiple, Candle};
use thiserror::Error;

type Result<T> = std::result::Result<T, ChandlerError>;

#[derive(Error, Debug)]
pub enum ChandlerError {
    #[error("missing candle(s) from start of period; cannot fill")]
    MissingStartCandles,
}

pub fn fill_missing_candles(
    interval: u64,
    start: u64,
    end: u64,
    candles: &[Candle],
) -> Result<Vec<Candle>> {
    let start = floor_multiple(start, interval);
    let end = floor_multiple(end, interval);
    let length = ((end - start) / interval) as usize;

    let mut candles_filled = Vec::with_capacity(length);
    let mut current = start;
    let mut prev_candle: Option<&Candle> = None;

    for candle in candles {
        debug_assert_eq!(candle.time % interval, 0);
        let diff = (candle.time - current) / interval;
        for i in 1..=diff {
            match prev_candle {
                None => return Err(ChandlerError::MissingStartCandles),
                Some(ref c) => candles_filled.push(Candle {
                    time: c.time + i as u64 * interval,
                    // open: c.open,
                    // high: c.high,
                    // low: c.low,
                    // close: c.close,
                    // volume: c.volume,
                    open: c.close,
                    high: c.close,
                    low: c.close,
                    close: c.close,
                    volume: 0.0,
                }),
            }
            current += interval;
        }

        candles_filled.push(*candle);
        current += interval;

        prev_candle = Some(candle);
    }

    if current != end {
        panic!("missing candle(s) from end of period; cannot fill");
    }
    assert_eq!(candles_filled.len(), length);

    Ok(candles_filled)
}

pub fn candles_to_prices(candles: &[Candle], multipliers: Option<&[f64]>) -> Vec<f64> {
    let mut prices = Vec::with_capacity(candles.len() + 1);
    prices.push(candles[0].open * multipliers.map_or(1.0, |m| m[0]));
    for i in 0..candles.len() {
        let multiplier_i = i + 1; // Has to be offset by 1.
        prices.push(candles[i].close * multipliers.map_or(1.0, |m| m[multiplier_i]));
    }
    prices
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fill_missing_candles() {
        let input = vec![
            Candle {
                time: 0,
                open: 2.0,
                high: 4.0,
                low: 1.0,
                close: 3.0,
                volume: 1.0,
            },
            Candle {
                time: 2,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
        ];
        let expected_output = vec![
            Candle {
                time: 0,
                open: 2.0,
                high: 4.0,
                low: 1.0,
                close: 3.0,
                volume: 1.0,
            },
            Candle {
                time: 1,
                open: 3.0,
                high: 3.0,
                low: 3.0,
                close: 3.0,
                volume: 0.0,
            },
            Candle {
                time: 2,
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
            },
        ];

        let output = fill_missing_candles(1, 0, 3, &input);

        assert!(output.is_ok());
        let output = output.unwrap();

        assert_eq!(output, expected_output);
        assert!(output
            .iter()
            .zip(expected_output.iter())
            .all(|(c1, c2)| c1.eq(c2)));
    }
}

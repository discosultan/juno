use crate::{math::floor_multiple_offset, storages, time::TimestampIntExt, Candle};
use once_cell::sync::Lazy;
use std::collections::HashMap;
use thiserror::Error;

type Result<T> = std::result::Result<T, ChandlerError>;

#[derive(Error, Debug)]
pub enum ChandlerError {
    #[error("missing candle(s) from the start of the period; cannot fill; start {start}, current {current}")]
    MissingStartCandles { start: String, current: String },
    #[error(
        "missing candle(s) from the end of the period; cannot fill; current {current}, end {end}"
    )]
    MissingEndCandles { current: String, end: String },
    #[error("{0}")]
    StorageError(#[from] storages::StorageError),
}

pub fn list_candles(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let interval_offset = get_interval_offset(interval);
    let start = floor_multiple_offset(start, interval, interval_offset);
    let end = floor_multiple_offset(end, interval, interval_offset);
    storages::list_candles(exchange, symbol, interval, start, end).map_err(|err| err.into())
}

pub fn list_candles_fill_missing(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let interval_offset = get_interval_offset(interval);
    let start = floor_multiple_offset(start, interval, interval_offset);
    let end = floor_multiple_offset(end, interval, interval_offset);
    let candles = storages::list_candles(exchange, symbol, interval, start, end)?;
    fill_missing_candles(interval, start, end, &candles)
}

pub(crate) fn fill_missing_candles(
    interval: u64,
    candle_start: u64,
    candle_end: u64,
    candles: &[Candle],
) -> Result<Vec<Candle>> {
    let interval_offset = get_interval_offset(interval);
    let start = floor_multiple_offset(candle_start, interval, interval_offset);
    let end = floor_multiple_offset(candle_end, interval, interval_offset);
    let length = ((end - start) / interval) as usize;

    let mut candles_filled = Vec::with_capacity(length);
    let mut current = start;
    let mut prev_candle: Option<&Candle> = None;

    for candle in candles {
        let diff = (candle.time - current) / interval;
        for i in 1..=diff {
            match prev_candle {
                None => {
                    return Err(ChandlerError::MissingStartCandles {
                        start: start.to_timestamp_repr(),
                        current: candle.time.to_timestamp_repr(),
                    })
                }
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
        return Err(ChandlerError::MissingEndCandles {
            current: current.to_timestamp_repr(),
            end: end.to_timestamp_repr(),
        });
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

static BINANCE_INTERVAL_OFFSETS: Lazy<HashMap<u64, u64>> = Lazy::new(|| {
    [
        (60000, 0),               // 1m
        (180000, 0),              // 3m
        (300000, 0),              // 5m
        (900000, 0),              // 15m
        (1800000, 0),             // 30m
        (3600000, 0),             // 1h
        (7200000, 0),             // 2h
        (14400000, 0),            // 4h
        (21600000, 0),            // 6h
        (28800000, 0),            // 8h
        (43200000, 0),            // 12h
        (86400000, 0),            // 1d
        (259200000, 0),           // 3d
        (604800000, 345600000),   // 1w 4d
        (2629746000, 2541726000), // 1M 4w1d10h2m6s
    ]
    .iter()
    .cloned()
    .collect()
});

pub fn map_interval_offsets() -> HashMap<u64, u64> {
    BINANCE_INTERVAL_OFFSETS.clone()
}

pub fn get_interval_offset(interval: u64) -> u64 {
    BINANCE_INTERVAL_OFFSETS
        .get(&interval)
        .map(|interval| *interval)
        .unwrap_or(0)
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

mod exchange;
mod storage;

use crate::{
    math::floor_multiple_offset,
    time::{deserialize_timestamp, serialize_timestamp, TimestampIntExt},
    utils::generate_missing_spans,
};
use serde::{Deserialize, Serialize};
use std::ops::AddAssign;
use thiserror::Error;

type Result<T> = std::result::Result<T, Error>;

pub use exchange::{get_interval_offset, map_interval_offsets};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
pub struct Candle {
    #[serde(serialize_with = "serialize_timestamp")]
    #[serde(deserialize_with = "deserialize_timestamp")]
    pub time: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

impl AddAssign<&Candle> for Candle {
    fn add_assign(&mut self, other: &Self) {
        self.high = f64::max(self.high, other.high);
        self.low = f64::min(self.low, other.low);
        self.close = other.close;
        self.volume += other.volume;
    }
}

#[derive(Error, Debug)]
pub enum Error {
    #[error("missing candle(s) from the start of the period; cannot fill; start {start}, current {current}")]
    MissingStartCandles { start: String, current: String },
    #[error(
        "missing candle(s) from the end of the period; cannot fill; current {current}, end {end}"
    )]
    MissingEndCandles { current: String, end: String },
    #[error("{0}")]
    Storage(#[from] storage::Error),
    #[error("{0}")]
    Exchange(#[from] exchange::Error),
}

pub async fn list_candles(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let interval_offset = get_interval_offset(interval);
    let start = floor_multiple_offset(start, interval, interval_offset);
    let end = floor_multiple_offset(end, interval, interval_offset);
    list_candles_internal(exchange, symbol, interval, start, end).await
}

pub async fn list_candles_fill_missing(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let interval_offset = get_interval_offset(interval);
    let start = floor_multiple_offset(start, interval, interval_offset);
    let end = floor_multiple_offset(end, interval, interval_offset);
    let candles = list_candles_internal(exchange, symbol, interval, start, end).await?;
    fill_missing_candles(interval, start, end, &candles)
}

async fn list_candles_internal(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let existing_spans = storage::list_candle_spans(exchange, symbol, interval, start, end).await?;
    let missing_spans = generate_missing_spans(start, end, &existing_spans);

    let mut spans = existing_spans
        .iter()
        .map(|(start, end)| (start, end, true))
        .chain(missing_spans.iter().map(|(start, end)| (start, end, false)))
        .collect::<Vec<_>>();
    spans.sort_by_key(|(start, _end, _exists)| *start);

    let mut result: Vec<Candle> = Vec::with_capacity(((end - start) / interval) as usize);
    for (&span_start, &span_end, exist_locally) in spans {
        let candles = if exist_locally {
            storage::list_candles(exchange, symbol, interval, span_start, span_end).await?
        } else {
            let candles =
                exchange::list_candles(symbol, interval, span_start, span_end).await?;
            candles
        };
        result.extend(candles);
    }

    Ok(result)
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
                    return Err(Error::MissingStartCandles {
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
        return Err(Error::MissingEndCandles {
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

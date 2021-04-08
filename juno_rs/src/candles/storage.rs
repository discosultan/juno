#![allow(dead_code)]

use super::Candle;
use crate::storage::{connect, get_f64, get_u64, Result};
use sqlx::sqlite::SqliteRow;

pub use crate::storage::Error;

pub async fn list_candle_spans(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<(u64, u64)>> {
    let shard = format!("{}_{}_{}", exchange, symbol, interval);

    let mut conn = connect(&shard).await?;
    let res: Vec<(u64, u64)> = sqlx::query(
        "SELECT start, end FROM candle_span WHERE start < ? AND end > ? ORDER BY start",
    )
    .bind(start as i64)
    .bind(end as i64)
    .map(|row: SqliteRow| (get_u64(&row, 0), get_u64(&row, 1)))
    .fetch_all(&mut conn)
    .await?;

    Ok(res)
}

pub async fn list_candles(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let shard = format!("{}_{}_{}", exchange, symbol, interval);

    let mut conn = connect(&shard).await?;
    let res: Vec<Candle> = sqlx::query(
        "SELECT time, open, high, low, close, volume FROM candle WHERE time >= ? AND time < ? \
        ORDER BY time",
    )
    .bind(start as i64)
    .bind(end as i64)
    .map(|row: SqliteRow| Candle {
        time: get_u64(&row, 0),
        open: get_f64(&row, 1),
        high: get_f64(&row, 2),
        low: get_f64(&row, 3),
        close: get_f64(&row, 4),
        volume: get_f64(&row, 5),
    })
    .fetch_all(&mut conn)
    .await?;

    Ok(res)
}

// NB! Careful with storing. We use a decimal datatype in Python to store monetary values. We use
// a double in Rust!

// pub async fn store_candles_and_span(
//     exchange: &str,
//     symbol: &str,
//     interval: u64,
//     start: u64,
//     end: u64,
//     items: &[Candle],
// ) -> Result<()> {
//     // Even if items list is empty, we still want to store a span for the period!
//     if items.len() > 0 {
//         let first_time = items[0].time;
//         let last_time = items[items.len() - 1].time;
//         if start > first_time {
//             return Err(Error::Unknown(format!(
//                 "Span start {} bigger than first item time {}",
//                 start, first_time
//             )));
//         }
//         if end <= last_time {
//             return Err(Error::Unknown(format!(
//                 "Span end {} smaller than or equal to last item time {}",
//                 end, last_time
//             )));
//         }
//     }
//     let shard = format!("{}_{}_{}", exchange, symbol, interval);
// }

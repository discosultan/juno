use super::Candle;
use crate::storage::{blob_to_f64, connect, Result};
use rusqlite::params;
use tokio::task;

pub use crate::storage::Error;

pub async fn list_candle_spans(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<(u64, u64)>> {
    let shard = format!("{}_{}_{}", exchange, symbol, interval);
    task::spawn_blocking(move || list_candle_spans_blocking(shard, start, end))
        .await.map_err(|err| Error::Unknown(format!("{:?}", err)))?
}

fn list_candle_spans_blocking(
    shard: String,
    start: u64,
    end: u64,
) -> Result<Vec<(u64, u64)>> {
    let conn = connect(&shard)?;
    let mut stmt = conn
        .prepare("SELECT start, end FROM candle_span WHERE start < ? AND end > ? ORDER BY start")?;
    let res = stmt.query_map(params![start, end], |row| Ok((row.get(0)?, row.get(1)?)))?;
    res.map(|r| r.map_err(|e| e.into())).collect()
}

pub async fn list_candles(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let shard = format!("{}_{}_{}", exchange, symbol, interval);
    task::spawn_blocking(move || list_candles_blocking(shard, start, end))
        .await.map_err(|err| Error::Unknown(format!("{:?}", err)))?
}

fn list_candles_blocking(
    shard: String,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let conn = connect(&shard)?;
    let mut stmt = conn.prepare(
        "SELECT time, open, high, low, close, volume FROM candle WHERE time >= ? AND time < ? \
        ORDER BY time",
    )?;
    let res = stmt.query_map(params![start, end], |row| {
        Ok(Candle {
            time: row.get(0)?,
            open: blob_to_f64(row.get(1)?)?,
            high: blob_to_f64(row.get(2)?)?,
            low: blob_to_f64(row.get(3)?)?,
            close: blob_to_f64(row.get(4)?)?,
            volume: blob_to_f64(row.get(5)?)?,
        })
    })?;
    res.map(|r| r.map_err(|e| e.into())).collect()
}

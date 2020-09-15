use crate::common::Candle;
use rusqlite::{params, Connection};
use std::error::Error;

pub fn list_candles(
    exchange: &str, symbol: &str, interval: u64, start: u64, end: u64
) -> Result<Vec<Candle>, Box<dyn Error>> {
    let shard = format!("{}_{}_{}", exchange, symbol, interval);
    let conn = Connection::open(format!("~/.juno/data/v47_{}.db", shard))?;
    let mut stmt = conn.prepare(
        "SELECT time, open, high, low, close, volume FROM candle WHERE time >= ? AND time < ? \
        ORDER BY time"
    )?;
    stmt
        .query_map(params![end as i64, start as i64], |row| {
            Ok(Candle {
                time: row.get::<_, i64>(0)? as u64,
                open: row.get(1)?,
                high: row.get(2)?,
                low: row.get(3)?,
                close: row.get(4)?,
                volume: row.get(5)?,
            })
        })
        .map_err(|e| e.into())
        ?.collect()
}

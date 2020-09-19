use rusqlite::{Connection, NO_PARAMS, params};
use serde::{Deserialize, Serialize};
use serde_json;
use std::error::Error;
use crate::common::{Candle, ExchangeInfo};

const VERSION: &str = "v48";

#[derive(Deserialize, Serialize)]
struct Timestamped<T> {
    pub time: u64,
    pub item: T,
}

fn blob_to_f64(blob: Vec<u8>) -> Result<f64, rusqlite::Error> {
    let s = std::str::from_utf8(&blob).map_err(|e| rusqlite::Error::Utf8Error(e))?;
    s.parse::<f64>()
        .map_err(|_| rusqlite::Error::ExecuteReturnedResults {})
}

pub fn list_candles(
    exchange: &str,
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>, Box<dyn Error>> {
    let shard = format!("{}_{}_{}", exchange, symbol, interval);
    let conn = Connection::open(format!("/home/discosultan/.juno/data/{}_{}.db", VERSION, shard))?;
    let mut stmt = conn.prepare(
        "SELECT time, open, high, low, close, volume FROM candle WHERE time >= ? AND time < ? \
        ORDER BY time",
    )?;
    let res = stmt.query_map(params![start as i64, end as i64], |row| {
        Ok(Candle {
            time: row.get::<_, i64>(0)? as u64,
            open: blob_to_f64(row.get(1)?)?,
            high: blob_to_f64(row.get(2)?)?,
            low: blob_to_f64(row.get(3)?)?,
            close: blob_to_f64(row.get(4)?)?,
            volume: blob_to_f64(row.get(5)?)?,
        })
    })?;
    res.map(|r| r.map_err(|e| e.into())).collect()
}

pub fn get_exchange_info(exchange: &str) -> Result<ExchangeInfo, Box<dyn Error>> {
    let shard = exchange;
    let conn = Connection::open(format!("/home/discosultan/.juno/data/{}_{}.db", VERSION, shard))?;
    let json = conn.query_row(
        "SELECT value FROM keyvaluepair WHERE key = 'exchange_info' LIMIT 1",
        NO_PARAMS,
        |row| row.get::<_, String>(0),
    )?;
    let res = serde_json::from_str::<Timestamped<ExchangeInfo>>(&json)?;
    Ok(res.item)
}

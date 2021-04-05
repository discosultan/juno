use crate::ExchangeInfo;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use thiserror::Error;

pub type Result<T> = std::result::Result<T, Error>;

const VERSION: &str = "v49";

#[derive(Error, Debug)]
pub enum Error {
    #[error("(de)serialization error")]
    Serde(#[from] serde_json::Error),
    #[error("sqlite error")]
    Sqlite(#[from] rusqlite::Error),
    #[error("unknown error")]
    Unknown(String),
}

#[derive(Deserialize, Serialize)]
struct Timestamped<T> {
    pub time: u64,
    pub item: T,
}

pub fn blob_to_f64(blob: Vec<u8>) -> std::result::Result<f64, rusqlite::Error> {
    let s = std::str::from_utf8(&blob).map_err(rusqlite::Error::Utf8Error)?;
    s.parse::<f64>()
        .map_err(|_| rusqlite::Error::ExecuteReturnedResults {})
}

pub fn connect(shard: &str) -> Result<Connection> {
    Connection::open(format!(
        "/home/discosultan/.juno/data/{}_{}.db",
        VERSION, shard
    ))
    .map_err(|err| err.into())
}

pub fn get_exchange_info(exchange: &str) -> Result<ExchangeInfo> {
    let shard = exchange;
    let conn = connect(shard)?;
    let json = conn.query_row(
        "SELECT value FROM keyvaluepair WHERE key = 'exchange_info' LIMIT 1",
        [],
        |row| row.get::<_, String>(0),
    )?;
    let res = serde_json::from_str::<Timestamped<ExchangeInfo>>(&json)?;
    Ok(res.item)
}

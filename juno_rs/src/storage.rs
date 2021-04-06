use crate::ExchangeInfo;
use serde::{Deserialize, Serialize};
use sqlx::{sqlite::SqliteConnection, sqlite::SqliteRow, ColumnIndex, Connection, Row};
use thiserror::Error;

pub type Result<T> = std::result::Result<T, Error>;

const VERSION: &str = "v49";

#[derive(Error, Debug)]
pub enum Error {
    #[error("(de)serialization error")]
    Serde(#[from] serde_json::Error),
    #[error("sqlite error")]
    Sqlite(#[from] sqlx::Error),
    #[error("unknown error")]
    Unknown(String),
}

#[derive(Deserialize, Serialize)]
struct Timestamped<T> {
    pub time: u64,
    pub item: T,
}

pub async fn connect(shard: &str) -> Result<SqliteConnection> {
    let conn = SqliteConnection::connect(&format!(
        "/home/discosultan/.juno/data/{}_{}.db",
        VERSION, shard
    ))
    .await?;

    Ok(conn)
}

pub async fn get_exchange_info(exchange: &str) -> Result<ExchangeInfo> {
    let shard = exchange;
    let mut conn = connect(shard).await?;
    let row: (String,) =
        sqlx::query_as("SELECT value FROM keyvaluepair WHERE key = 'exchange_info' LIMIT 1")
            .fetch_one(&mut conn)
            .await?;
    let res = serde_json::from_str::<Timestamped<ExchangeInfo>>(&row.0)?;
    Ok(res.item)
}

// TODO: We could implement sqlx encode and decode traits for timestamp and decimal types.
// However, because we are not using local types, we cannot impl the traits. Could be solved with
// a newtype pattern.
pub fn get_u64<'r, I>(row: &'r SqliteRow, index: I) -> u64
where
    I: ColumnIndex<SqliteRow>,
{
    row.get::<i64, I>(index) as u64
}

pub fn get_f64<'r, I>(row: &'r SqliteRow, index: I) -> f64
where
    I: ColumnIndex<SqliteRow>,
{
    std::str::from_utf8(&row.get::<Vec<u8>, I>(index)).unwrap().parse::<f64>().unwrap()
}

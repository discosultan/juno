use super::Candle;
use crate::{time::IntervalIntExt, utils::page};
use once_cell::sync::Lazy;
use std::collections::HashMap;
use thiserror::Error;

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Error, Debug)]
pub enum Error {
    #[error("{0}")]
    Reqwest(#[from] reqwest::Error),
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

const CANDLES_URL: &'static str = "https://api.binance.com/api/v3/klines";
const CANDLES_LIMIT: u64 = 1000; // Max possible candles per request.
const CANDLES_LIMIT_STR: &'static str = "1000";

type KlinesResponse = (
    u64,
    String,
    String,
    String,
    String,
    String,
    u64,
    String,
    u64,
    String,
    String,
    String,
);

pub async fn list_candles(
    symbol: &str,
    interval: u64,
    start: u64,
    end: u64,
) -> Result<Vec<Candle>> {
    let mut result = Vec::with_capacity(((end - start) / interval) as usize);

    let binance_interval = interval.to_interval_repr();
    let binance_symbol = to_http_symbol(symbol);

    let client = reqwest::Client::new();

    // Start 0 is a special value indicating that we try to find the earliest available candle.
    let pagination_interval = if start == 0 { end - start } else { interval };
    for (page_start, page_end) in page(start, end, pagination_interval, CANDLES_LIMIT) {
        let response = client
            .get(CANDLES_URL)
            .query(&[
                ("symbol", binance_symbol.as_ref()),
                ("interval", binance_interval.as_ref()),
                ("startTime", page_start.to_string().as_ref()),
                ("endTime", (page_end - 1).to_string().as_ref()),
                ("limit", CANDLES_LIMIT_STR),
            ])
            .send()
            .await?
            .json::<Vec<KlinesResponse>>()
            .await?;
        result.extend(response.iter().map(|c| Candle {
            time: c.0,
            open: c.1.parse().unwrap(),
            high: c.2.parse().unwrap(),
            low: c.3.parse().unwrap(),
            close: c.4.parse().unwrap(),
            volume: c.5.parse().unwrap(),
        }));
    }

    Ok(result)
}

fn to_http_symbol(symbol: &str) -> String {
    symbol.replace("-", "").to_ascii_uppercase()
}

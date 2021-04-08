pub mod candles;
pub mod easing;
pub mod filters;
pub mod genetics;
pub mod indicators;
pub mod itertools;
pub mod math;
pub mod statistics;
pub mod stop_loss;
pub mod storage;
pub mod strategies;
pub mod take_profit;
pub mod time;
pub mod trading;
pub mod utils;

pub use crate::{candles::Candle, filters::Filters};

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

pub trait SymbolExt {
    fn assets(&self) -> (&str, &str);
    fn base_asset(&self) -> &str;
    fn quote_asset(&self) -> &str;
}

impl SymbolExt for str {
    fn assets(&self) -> (&str, &str) {
        let dash_i = dash_index(self);
        (&self[..dash_i], &self[dash_i..])
    }
    fn base_asset(&self) -> &str {
        &self[..dash_index(self)]
    }
    fn quote_asset(&self) -> &str {
        &self[dash_index(self)..]
    }
}

fn dash_index(value: &str) -> usize {
    value.find('-').expect("not a valid symbol")
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Advice {
    None,
    Long,
    Short,
    Liquidate,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct BorrowInfo {
    pub daily_interest_rate: f64,
    pub limit: f64,
}

#[derive(Deserialize, Serialize)]
pub struct AssetInfo {
    pub precision: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

#[derive(Deserialize, Serialize)]
pub struct ExchangeInfo {
    // Key: asset
    pub assets: HashMap<String, AssetInfo>,
    // Key: symbol
    pub fees: HashMap<String, Fees>,
    // Key: symbol
    pub filters: HashMap<String, Filters>,
    // Keys: account, asset
    pub borrow_info: HashMap<String, HashMap<String, BorrowInfo>>,
}

#[derive(Deserialize, Serialize)]
pub struct Fill {
    pub price: f64,
    pub size: f64,
    pub quote: f64,
    pub fee: f64,
}

impl Fill {
    pub fn total_size(fills: &[Fill]) -> f64 {
        fills.iter().map(|fill| fill.size).sum()
    }

    pub fn total_quote(fills: &[Fill]) -> f64 {
        fills.iter().map(|fill| fill.quote).sum()
    }

    pub fn total_fee(fills: &[Fill]) -> f64 {
        fills.iter().map(|fill| fill.fee).sum()
    }
}

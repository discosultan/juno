pub mod chandler;
pub mod easing;
pub mod filters;
pub mod genetics;
pub mod indicators;
pub mod itertools;
pub mod math;
pub mod statistics;
pub mod stop_loss;
pub mod storages;
pub mod strategies;
pub mod take_profit;
pub mod time;
pub mod trading;
pub mod utils;

pub use crate::filters::Filters;

use crate::time::serialize_timestamp;
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, ops::AddAssign};

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

#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
pub struct Candle {
    #[serde(serialize_with = "serialize_timestamp")]
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

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

#[derive(Deserialize, Serialize)]
pub struct ExchangeInfo {
    pub fees: HashMap<String, Fees>,
    pub filters: HashMap<String, Filters>,
    pub borrow_info: HashMap<String, HashMap<String, BorrowInfo>>,
}

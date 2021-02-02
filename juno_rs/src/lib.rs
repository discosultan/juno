pub mod chandler;
pub mod easing;
pub mod ffi;
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

pub use crate::{ffi::*, filters::Filters, math::floor_multiple};

use crate::time::serialize_timestamp;
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
#[repr(C)]
pub struct BorrowInfo {
    pub daily_interest_rate: f64,
    pub limit: f64,
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq)]
#[repr(C)]
pub struct Candle {
    #[serde(serialize_with = "serialize_timestamp")]
    pub time: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[repr(C)]
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

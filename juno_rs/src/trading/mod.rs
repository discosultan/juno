mod evaluation;
mod traders;

pub use evaluation::*;
pub use traders::*;

use crate::{genetics::Chromosome, time::serialize_timestamp};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

pub const MISSED_CANDLE_POLICY_IGNORE: u32 = 0;
pub const MISSED_CANDLE_POLICY_RESTART: u32 = 1;
pub const MISSED_CANDLE_POLICY_LAST: u32 = 2;

pub const MISSED_CANDLE_POLICIES_LEN: u32 = 3;

#[derive(AggregateChromosome, Clone, Debug, Serialize)]
pub struct TradingChromosome<T: Chromosome, U: Chromosome, V: Chromosome> {
    pub trader: TraderParams,
    pub strategy: T,
    pub stop_loss: U,
    pub take_profit: V,
}

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct TraderParams {
    #[serde(serialize_with = "serialize_missed_candle_policy")]
    #[serde(deserialize_with = "deserialize_missed_candle_policy")]
    pub missed_candle_policy: u32,
}

fn missed_candle_policy(rng: &mut StdRng) -> u32 {
    rng.gen_range(0, MISSED_CANDLE_POLICIES_LEN)
}

#[derive(Clone, Copy, Debug, Serialize)]
pub enum CloseReason {
    Strategy,
    Cancelled,
    StopLoss,
    TakeProfit,
}

pub enum OpenPosition {
    Long(OpenLongPosition),
    Short(OpenShortPosition),
}

pub struct OpenLongPosition {
    pub time: u64,
    pub quote: f64,
    pub size: f64,
    pub fee: f64,
}

impl OpenLongPosition {
    pub fn close(
        &self,
        time: u64,
        size: f64,
        quote: f64,
        fee: f64,
        reason: CloseReason,
    ) -> LongPosition {
        LongPosition {
            open_time: self.time,
            open_quote: self.quote,
            open_size: self.size,
            open_fee: self.fee,

            close_time: time,
            close_size: size,
            close_quote: quote,
            close_fee: fee,
            close_reason: reason,
        }
    }

    #[inline]
    pub fn cost(&self) -> f64 {
        self.quote
    }

    pub fn base_gain(&self) -> f64 {
        self.size - self.fee
    }
}

pub struct OpenShortPosition {
    pub time: u64,
    pub collateral: f64,
    pub borrowed: f64,
    pub quote: f64,
    pub fee: f64,
}

impl OpenShortPosition {
    pub fn close(&self, time: u64, quote: f64, reason: CloseReason) -> ShortPosition {
        ShortPosition {
            open_time: self.time,
            collateral: self.collateral,
            borrowed: self.borrowed,
            open_quote: self.quote,
            open_fee: self.fee,

            close_time: time,
            close_quote: quote,
            close_reason: reason,
        }
    }

    #[inline]
    pub fn collateral(&self) -> f64 {
        self.quote
    }
}

#[derive(Debug, Serialize)]
#[serde(tag = "type")]
pub enum Position {
    Long(LongPosition),
    Short(ShortPosition),
}

#[derive(Debug, Serialize)]
pub struct LongPosition {
    #[serde(serialize_with = "serialize_timestamp")]
    pub open_time: u64,
    pub open_quote: f64,
    pub open_size: f64,
    pub open_fee: f64,

    #[serde(serialize_with = "serialize_timestamp")]
    pub close_time: u64,
    pub close_size: f64,
    pub close_quote: f64,
    pub close_fee: f64,
    pub close_reason: CloseReason,
}

impl LongPosition {
    #[inline]
    pub fn cost(&self) -> f64 {
        self.open_quote
    }

    pub fn base_gain(&self) -> f64 {
        self.open_size - self.open_fee
    }

    #[inline]
    pub fn base_cost(&self) -> f64 {
        self.close_size
    }

    pub fn gain(&self) -> f64 {
        self.close_quote - self.close_fee
    }

    pub fn profit(&self) -> f64 {
        self.gain() - self.cost()
    }

    pub fn duration(&self) -> u64 {
        self.close_time - self.open_time
    }
}

#[derive(Debug, Serialize)]
pub struct ShortPosition {
    #[serde(serialize_with = "serialize_timestamp")]
    pub open_time: u64,
    pub collateral: f64,
    pub borrowed: f64,
    pub open_quote: f64,
    pub open_fee: f64,
    #[serde(serialize_with = "serialize_timestamp")]
    pub close_time: u64,
    pub close_quote: f64,
    pub close_reason: CloseReason,
}

impl ShortPosition {
    #[inline]
    pub fn cost(&self) -> f64 {
        self.collateral
    }

    #[inline]
    pub fn base_gain(&self) -> f64 {
        self.borrowed
    }

    #[inline]
    pub fn base_cost(&self) -> f64 {
        self.borrowed
    }

    pub fn gain(&self) -> f64 {
        self.open_quote - self.open_fee + self.collateral - self.close_quote
    }

    pub fn duration(&self) -> u64 {
        self.close_time - self.open_time
    }

    pub fn profit(&self) -> f64 {
        self.gain() - self.cost()
    }
}

#[derive(Debug, Serialize)]
pub struct TradingSummary {
    pub positions: Vec<Position>,

    #[serde(serialize_with = "serialize_timestamp")]
    pub start: u64,
    #[serde(serialize_with = "serialize_timestamp")]
    pub end: u64,
    pub quote: f64,
}

impl TradingSummary {
    pub fn new(start: u64, end: u64, quote: f64) -> Self {
        Self {
            positions: Vec::new(),
            start,
            end,
            quote,
        }
    }
}

fn serialize_missed_candle_policy<S>(value: &u32, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    let representation = match *value {
        MISSED_CANDLE_POLICY_IGNORE => "ignore",
        MISSED_CANDLE_POLICY_LAST => "last",
        MISSED_CANDLE_POLICY_RESTART => "restart",
        _ => panic!("unknown missed candle policy value: {}", value),
    };
    serializer.serialize_str(representation)
}

#[allow(dead_code)]
fn deserialize_missed_candle_policy<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: String = Deserialize::deserialize(deserializer)?;
    Ok(match representation.as_ref() {
        "ignore" => MISSED_CANDLE_POLICY_IGNORE,
        "last" => MISSED_CANDLE_POLICY_LAST,
        "restart" => MISSED_CANDLE_POLICY_RESTART,
        _ => panic!(
            "unknown missed candle policy representation: {}",
            representation
        ),
    })
}

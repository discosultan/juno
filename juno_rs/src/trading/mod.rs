mod evaluation;
mod traders;

pub use evaluation::*;
pub use traders::*;

use crate::{
    genetics::Chromosome,
    time::{deserialize_intervals, serialize_interval, serialize_intervals, serialize_timestamp},
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{ser::SerializeSeq, Deserialize, Deserializer, Serialize, Serializer};
use std::mem;

pub const MISSED_CANDLE_POLICY_IGNORE: u32 = 0;
pub const MISSED_CANDLE_POLICY_RESTART: u32 = 1;
pub const MISSED_CANDLE_POLICY_LAST: u32 = 2;

pub const MISSED_CANDLE_POLICIES_LEN: u32 = 3;

#[derive(Chromosome, Clone, Debug, Serialize)]
pub struct TradingParams<T: Chromosome, U: Chromosome, V: Chromosome> {
    #[chromosome]
    pub strategy: T,
    #[chromosome]
    pub stop_loss: U,
    #[chromosome]
    pub take_profit: V,
    #[chromosome]
    pub trader: TraderParams,
}

#[derive(Clone, Debug, Serialize)]
pub struct TraderParams {
    #[serde(serialize_with = "serialize_interval")]
    pub interval: u64,
    #[serde(serialize_with = "serialize_missed_candle_policy")]
    pub missed_candle_policy: u32,
}

#[derive(Default, Deserialize, Serialize)]
pub struct TraderParamsContext {
    #[serde(deserialize_with = "deserialize_intervals")]
    #[serde(serialize_with = "serialize_intervals")]
    pub intervals: Vec<u64>,
    #[serde(deserialize_with = "deserialize_missed_candle_policies")]
    #[serde(serialize_with = "serialize_missed_candle_policies")]
    pub missed_candle_policies: Vec<u32>,
}

impl Chromosome for TraderParams {
    type Context = TraderParamsContext;

    fn len() -> usize {
        2
    }

    fn generate(rng: &mut StdRng, ctx: &Self::Context) -> Self {
        Self {
            interval: match ctx.intervals.len() {
                0 => panic!(),
                1 => ctx.intervals[0],
                _ => *ctx.intervals.choose(rng).unwrap(),
            },
            missed_candle_policy: match ctx.missed_candle_policies.len() {
                0 => panic!(),
                1 => ctx.missed_candle_policies[0],
                _ => *ctx.missed_candle_policies.choose(rng).unwrap(),
            },
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        match i {
            0 => mem::swap(&mut self.interval, &mut other.interval),
            1 => mem::swap(
                &mut self.missed_candle_policy,
                &mut other.missed_candle_policy,
            ),
            _ => panic!(),
        };
    }

    fn mutate(&mut self, rng: &mut StdRng, _i: usize, ctx: &Self::Context) {
        self.interval = Self::generate(rng, ctx).interval;
    }
}

// fn missed_candle_policy(rng: &mut StdRng) -> u32 {
//     rng.gen_range(0..MISSED_CANDLE_POLICIES_LEN)
// }

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
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

fn missed_candle_policy_to_str(value: u32) -> &'static str {
    match value {
        MISSED_CANDLE_POLICY_IGNORE => "ignore",
        MISSED_CANDLE_POLICY_LAST => "last",
        MISSED_CANDLE_POLICY_RESTART => "restart",
        _ => panic!("unknown missed candle policy value: {}", value),
    }
}

fn str_to_missed_candle_policy(representation: &str) -> u32 {
    match representation {
        "ignore" => MISSED_CANDLE_POLICY_IGNORE,
        "last" => MISSED_CANDLE_POLICY_LAST,
        "restart" => MISSED_CANDLE_POLICY_RESTART,
        _ => panic!(
            "unknown missed candle policy representation: {}",
            representation
        ),
    }
}

pub fn serialize_missed_candle_policy<S>(value: &u32, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    serializer.serialize_str(missed_candle_policy_to_str(*value))
}

pub fn deserialize_missed_candle_policy<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: String = Deserialize::deserialize(deserializer)?;
    Ok(str_to_missed_candle_policy(&representation))
}

pub fn serialize_missed_candle_policy_option<S>(
    value: &Option<u32>,
    serializer: S,
) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    match value {
        Some(value) => serializer.serialize_str(missed_candle_policy_to_str(*value)),
        None => serializer.serialize_none(),
    }
}

pub fn deserialize_missed_candle_policy_option<'de, D>(
    deserializer: D,
) -> Result<Option<u32>, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: Option<String> = Deserialize::deserialize(deserializer)?;
    Ok(representation.map(|repr| str_to_missed_candle_policy(&repr)))
}

pub fn serialize_missed_candle_policies<S>(values: &[u32], serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    let mut seq = serializer.serialize_seq(Some(values.len()))?;
    for value in values {
        seq.serialize_element(missed_candle_policy_to_str(*value))?;
    }
    seq.end()
}

pub fn deserialize_missed_candle_policies<'de, D>(deserializer: D) -> Result<Vec<u32>, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: Vec<String> = Deserialize::deserialize(deserializer)?;
    Ok(representation
        .iter()
        .map(|repr| str_to_missed_candle_policy(repr))
        .collect())
}

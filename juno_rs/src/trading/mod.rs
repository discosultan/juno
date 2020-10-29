mod evaluation;
mod traders;

pub use evaluation::*;
pub use traders::*;

use crate::{genetics::Chromosome, math::annualized, time::serialize_timestamp, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

pub const MISSED_CANDLE_POLICY_IGNORE: u32 = 0;
pub const MISSED_CANDLE_POLICY_RESTART: u32 = 1;
pub const MISSED_CANDLE_POLICY_LAST: u32 = 2;

pub const MISSED_CANDLE_POLICIES_LEN: u32 = 3;

#[derive(Clone, Debug, Serialize)]
pub struct TradingChromosome<T: Chromosome> {
    pub trader: TraderParams,
    pub strategy: T,
}

impl<T: Chromosome> Chromosome for TradingChromosome<T> {
    fn len() -> usize {
        TraderParams::len() + T::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            trader: TraderParams::generate(rng),
            strategy: T::generate(rng),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        if i < TraderParams::len() {
            self.trader.cross(&mut other.trader, i);
        } else {
            self.strategy
                .cross(&mut other.strategy, i - TraderParams::len());
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        if i < TraderParams::len() {
            self.trader.mutate(rng, i);
        } else {
            self.strategy.mutate(rng, i - TraderParams::len());
        }
    }
}

#[derive(Chromosome, Clone, Debug, Serialize)]
pub struct TraderParams {
    #[serde(serialize_with = "serialize_missed_candle_policy")]
    #[serde(deserialize_with = "deerialize_missed_candle_policy")]
    pub missed_candle_policy: u32,
    pub stop_loss: f64,
    pub trail_stop_loss: bool,
    pub take_profit: f64,
}

fn missed_candle_policy(rng: &mut StdRng) -> u32 {
    rng.gen_range(0, MISSED_CANDLE_POLICIES_LEN)
}
fn stop_loss(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) {
        0.0
    } else {
        rng.gen_range(0.0001, 0.9999)
    }
}
fn trail_stop_loss(rng: &mut StdRng) -> bool {
    rng.gen_bool(0.5)
}
fn take_profit(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) {
        0.0
    } else {
        rng.gen_range(0.0001, 9.9999)
    }
}

pub struct StopLoss {
    pub threshold: f64,
    trail: bool,
    close_at_position: f64,
    highest_close_since_position: f64,
    lowest_close_since_position: f64,
    close: f64,
}

impl StopLoss {
    pub fn new(threshold: f64, trail: bool) -> Self {
        Self {
            threshold,
            trail,
            close_at_position: 0.0,
            highest_close_since_position: 0.0,
            lowest_close_since_position: f64::MAX,
            close: 0.0,
        }
    }

    pub fn upside_hit(&self) -> bool {
        self.threshold > 0.0
            && self.close
                <= if self.trail {
                    self.highest_close_since_position
                } else {
                    self.close_at_position
                } * (1.0 - self.threshold)
    }

    pub fn downside_hit(&self) -> bool {
        self.threshold > 0.0
            && self.close
                >= if self.trail {
                    self.lowest_close_since_position
                } else {
                    self.close_at_position
                } * (1.0 + self.threshold)
    }

    pub fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
        self.highest_close_since_position = candle.close;
        self.lowest_close_since_position = candle.close;
    }

    pub fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
        self.highest_close_since_position =
            f64::max(self.highest_close_since_position, candle.close);
        self.lowest_close_since_position = f64::min(self.lowest_close_since_position, candle.close);
    }
}

pub struct TakeProfit {
    pub threshold: f64,
    close_at_position: f64,
    close: f64,
}

impl TakeProfit {
    pub fn new(threshold: f64) -> Self {
        Self {
            threshold,
            close_at_position: 0.0,
            close: 0.0,
        }
    }

    pub fn upside_hit(&self) -> bool {
        self.threshold > 0.0 && self.close >= self.close_at_position * (1.0 + self.threshold)
    }

    pub fn downside_hit(&self) -> bool {
        self.threshold > 0.0 && self.close <= self.close_at_position * (1.0 - self.threshold)
    }

    pub fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
    }

    pub fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
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
    pub time: u64,
    pub price: f64,
    pub cost: f64,
    pub base_gain: f64,
    pub base_cost: f64,

    #[serde(serialize_with = "serialize_timestamp")]
    pub close_time: u64,
    pub duration: u64,
    pub gain: f64,
    pub profit: f64,
    pub roi: f64,
    pub annualized_roi: f64,
}

impl LongPosition {
    pub fn new(time: u64, price: f64, size: f64, quote: f64, fee: f64) -> Self {
        Self {
            time,
            price,
            cost: quote,
            base_gain: size - fee,

            base_cost: 0.0,
            close_time: 0,
            duration: 0,
            gain: 0.0,
            profit: 0.0,
            roi: 0.0,
            annualized_roi: 0.0,
        }
    }

    pub fn close(&mut self, time: u64, _price: f64, size: f64, quote: f64, fee: f64) {
        self.close_time = time;
        self.duration = time - self.time;
        self.base_cost = size;
        self.gain = quote - fee;
        self.profit = self.gain - self.cost;
        self.roi = self.profit / self.cost;
        self.annualized_roi = annualized(self.duration, self.roi);
    }
}

#[derive(Debug, Serialize)]
pub struct ShortPosition {
    #[serde(serialize_with = "serialize_timestamp")]
    pub time: u64,
    pub collateral: f64,
    pub borrowed: f64,
    pub price: f64,
    pub quote: f64,
    pub fee: f64,
    pub cost: f64,
    pub base_gain: f64,
    pub base_cost: f64,

    #[serde(serialize_with = "serialize_timestamp")]
    pub close_time: u64,
    pub interest: f64,
    pub duration: u64,
    pub gain: f64,
    pub profit: f64,
    pub roi: f64,
    pub annualized_roi: f64,
}

impl ShortPosition {
    pub fn new(
        time: u64,
        collateral: f64,
        borrowed: f64,
        price: f64,
        _size: f64,
        quote: f64,
        fee: f64,
    ) -> Self {
        Self {
            time,
            collateral,
            borrowed,
            price,
            quote,
            fee,
            cost: collateral,
            base_gain: borrowed,

            base_cost: borrowed,
            close_time: 0,
            interest: 0.0,
            duration: 0,
            gain: 0.0,
            profit: 0.0,
            roi: 0.0,
            annualized_roi: 0.0,
        }
    }

    pub fn close(
        &mut self,
        interest: f64,
        time: u64,
        _price: f64,
        _size: f64,
        quote: f64,
        _fee: f64,
    ) {
        self.interest = interest;
        self.close_time = time;
        self.duration = time - self.time;
        self.gain = self.quote - self.fee + self.collateral - quote;
        self.profit = self.gain - self.cost;
        self.roi = self.profit / self.cost;
        self.annualized_roi = annualized(self.duration, self.roi);
    }
}

#[derive(Debug, Serialize)]
pub struct TradingSummary {
    pub positions: Vec<Position>,
    pub start: u64,
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
    let representation: &str = Deserialize::deserialize(deserializer)?;
    Ok(match representation {
        "ignore" => MISSED_CANDLE_POLICY_IGNORE,
        "last" => MISSED_CANDLE_POLICY_LAST,
        "restart" => MISSED_CANDLE_POLICY_RESTART,
        _ => panic!(
            "unknown missed candle policy representation: {}",
            representation
        ),
    })
}

mod evaluation;
mod traders;

pub use evaluation::*;
pub use traders::*;

use crate::{genetics::Chromosome, prelude::*};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::mem;

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub enum MissedCandlePolicy {
    Ignore,
    Restart,
    Last,
}

const MISSED_CANDLE_POLICY_CHOICES: [MissedCandlePolicy; 3] = [
    MissedCandlePolicy::Ignore,
    MissedCandlePolicy::Restart,
    MissedCandlePolicy::Last,
];

pub trait StdRngExt {
    fn gen_missed_candle_policy(&mut self) -> MissedCandlePolicy;
}

impl StdRngExt for StdRng {
    fn gen_missed_candle_policy(&mut self) -> MissedCandlePolicy {
        *MISSED_CANDLE_POLICY_CHOICES.choose(self).unwrap()
    }
}

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
    pub interval: Interval,
    pub missed_candle_policy: MissedCandlePolicy,
}

#[derive(Default, Deserialize, Serialize)]
pub struct TraderParamsContext {
    pub intervals: Vec<Interval>,
    pub missed_candle_policies: Vec<MissedCandlePolicy>,
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

    fn mutate(&mut self, rng: &mut StdRng, i: usize, ctx: &Self::Context) {
        match i {
            0 => {
                self.interval = match ctx.intervals.len() {
                    0 => panic!(),
                    1 => ctx.intervals[0],
                    _ => *ctx.intervals.choose(rng).unwrap(),
                }
            }
            1 => {
                self.missed_candle_policy = match ctx.missed_candle_policies.len() {
                    0 => panic!(),
                    1 => ctx.missed_candle_policies[0],
                    _ => *ctx.missed_candle_policies.choose(rng).unwrap(),
                }
            }
            _ => panic!(),
        };
    }
}

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
    pub time: Timestamp,
    pub quote: f64,
    pub size: f64,
    pub fee: f64,
}

impl OpenLongPosition {
    pub fn close(
        &self,
        time: Timestamp,
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
    pub time: Timestamp,
    pub collateral: f64,
    pub borrowed: f64,
    pub quote: f64,
    pub fee: f64,
}

impl OpenShortPosition {
    pub fn close(&self, time: Timestamp, quote: f64, reason: CloseReason) -> ShortPosition {
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
    pub open_time: Timestamp,
    pub open_quote: f64,
    pub open_size: f64,
    pub open_fee: f64,

    pub close_time: Timestamp,
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

    pub fn duration(&self) -> Interval {
        self.close_time - self.open_time
    }
}

#[derive(Debug, Serialize)]
pub struct ShortPosition {
    pub open_time: Timestamp,
    pub collateral: f64,
    pub borrowed: f64,
    pub open_quote: f64,
    pub open_fee: f64,
    pub close_time: Timestamp,
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

    pub fn duration(&self) -> Interval {
        self.close_time - self.open_time
    }

    pub fn profit(&self) -> f64 {
        self.gain() - self.cost()
    }
}

#[derive(Debug, Serialize)]
pub struct TradingSummary {
    pub positions: Vec<Position>,

    pub start: Timestamp,
    pub end: Timestamp,
    pub quote: f64,
}

impl TradingSummary {
    pub fn new(start: Timestamp, end: Timestamp, quote: f64) -> Self {
        Self {
            positions: Vec::new(),
            start,
            end,
            quote,
        }
    }
}

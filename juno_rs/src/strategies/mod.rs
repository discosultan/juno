mod double_ma;
mod double_ma_2;
mod four_week_rule;
mod macd;
mod rsi;
mod sig;
mod sig_osc;
mod single_ma;
mod triple_ma;

pub use double_ma::{DoubleMA, DoubleMAParams};
pub use double_ma_2::{DoubleMA2, DoubleMA2Params};
pub use four_week_rule::{FourWeekRule, FourWeekRuleParams};
pub use macd::{Macd, MacdParams};
pub use rsi::{Rsi, RsiParams};
pub use sig::{Sig, SigParams};
pub use sig_osc::{EnforceOscillatorFilter, PreventOscillatorFilter, SigOsc, SigOscParams};
pub use single_ma::{SingleMA, SingleMAParams};
pub use triple_ma::{TripleMA, TripleMAParams};

use crate::{
    genetics::Chromosome,
    indicators::{adler32, MA_CHOICES},
    Advice, Candle,
};
use rand::prelude::*;
use serde::{de::DeserializeOwned, Deserialize, Deserializer, Serialize, Serializer};
use std::cmp::min;

pub trait Strategy: Clone + Send + Sync {
    fn maturity(&self) -> u32;
    fn mature(&self) -> bool;
    fn update(&mut self, candle: &Candle);
}

pub trait Oscillator: Strategy {
    fn overbought(&self) -> bool;
    fn oversold(&self) -> bool;
}

pub trait Signal: Strategy {
    fn advice(&self) -> Advice;
}

pub struct MidTrend {
    policy: u32,
    previous: Option<Advice>,
    enabled: bool,
}

impl MidTrend {
    pub const POLICY_CURRENT: u32 = 0;
    pub const POLICY_PREVIOUS: u32 = 1;
    pub const POLICY_IGNORE: u32 = 2;

    pub const POLICIES_LEN: u32 = 3;

    pub fn new(policy: u32) -> Self {
        Self {
            policy,
            previous: None,
            enabled: true,
        }
    }

    pub fn maturity(&self) -> u32 {
        if self.policy == Self::POLICY_CURRENT {
            0
        } else {
            1
        }
    }

    pub fn update(&mut self, value: Advice) -> Advice {
        if !self.enabled || self.policy != MidTrend::POLICY_IGNORE {
            return value;
        }

        let mut result = Advice::None;
        if self.previous.is_none() {
            self.previous = Some(value)
        } else if Some(value) != self.previous {
            self.enabled = false;
            result = value;
        }
        result
    }
}

struct Persistence {
    age: u32,
    level: u32,
    return_previous: bool,
    potential: Advice,
    previous: Advice,
}

impl Persistence {
    pub fn new(level: u32, return_previous: bool) -> Self {
        Self {
            age: 0,
            level,
            return_previous,
            potential: Advice::None,
            previous: Advice::None,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.level
    }

    pub fn update(&mut self, value: Advice) -> Advice {
        if self.level == 0 {
            return value;
        }

        if value != self.potential {
            self.age = 0;
            self.potential = value;
        }

        let result = if self.age >= self.level {
            self.previous = self.potential;
            self.potential
        } else if self.return_previous {
            self.previous
        } else {
            Advice::None
        };

        self.age = min(self.age + 1, self.level);
        result
    }
}

pub struct Changed {
    previous: Advice,
    enabled: bool,
}

impl Changed {
    pub fn new(enabled: bool) -> Self {
        Self {
            previous: Advice::None,
            enabled,
        }
    }

    pub fn maturity(&self) -> u32 {
        0
    }

    pub fn update(&mut self, value: Advice) -> Advice {
        if !self.enabled {
            return value;
        }

        let result = if value != self.previous {
            value
        } else {
            Advice::None
        };
        self.previous = value;
        result
    }
}

pub fn combine(advice1: Advice, advice2: Advice) -> Advice {
    if advice1 == Advice::None || advice2 == Advice::None {
        Advice::None
    } else if advice1 == advice2 {
        advice1
    } else {
        Advice::Liquidate
    }
}

pub trait StdRngExt {
    fn gen_mid_trend_policy(&mut self) -> u32;
    fn gen_ma(&mut self) -> u32;
}

impl StdRngExt for StdRng {
    fn gen_mid_trend_policy(&mut self) -> u32 {
        self.gen_range(0, MidTrend::POLICIES_LEN)
    }

    fn gen_ma(&mut self) -> u32 {
        MA_CHOICES[self.gen_range(0, MA_CHOICES.len())]
    }
}

pub fn serialize_mid_trend_policy<S>(value: &u32, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    let representation = match *value {
        MidTrend::POLICY_CURRENT => "current",
        MidTrend::POLICY_IGNORE => "ignore",
        MidTrend::POLICY_PREVIOUS => "previous",
        _ => panic!("unknown mid trend policy value: {}", value),
    };
    serializer.serialize_str(representation)
}

pub fn deserialize_mid_trend_policy<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: String = Deserialize::deserialize(deserializer)?;
    Ok(match representation.as_ref() {
        "current" => MidTrend::POLICY_CURRENT,
        "ignore" => MidTrend::POLICY_IGNORE,
        "previous" => MidTrend::POLICY_PREVIOUS,
        _ => panic!(
            "unknown mid trend policy representation: {}",
            representation
        ),
    })
}

pub fn serialize_ma<S>(value: &u32, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    let representation = match *value {
        adler32::ALMA => "alma",
        adler32::DEMA => "dema",
        adler32::EMA => "ema",
        adler32::EMA2 => "ema2",
        adler32::KAMA => "kama",
        adler32::SMA => "sma",
        adler32::SMMA => "smma",
        _ => panic!("unknown ma value: {}", value),
    };
    serializer.serialize_str(representation)
}

pub fn deserialize_ma<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: String = Deserialize::deserialize(deserializer)?;
    Ok(match representation.as_ref() {
        "alma" => adler32::ALMA,
        "dema" => adler32::DEMA,
        "ema" => adler32::EMA,
        "ema2" => adler32::EMA2,
        "kama" => adler32::KAMA,
        "sma" => adler32::SMA,
        "smma" => adler32::SMMA,
        _ => panic!("unknown ma representation: {}", representation),
    })
}

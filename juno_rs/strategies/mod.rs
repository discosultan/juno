// mod double_ma;
mod four_week_rule;
// mod macd;
// mod macdrsi;
// mod mamacx;
// mod rsi;
// mod single_ma;
// mod triple_ma;

// pub use double_ma::{DoubleMA, DoubleMAParams};
pub use four_week_rule::{FourWeekRule, FourWeekRuleParams};
// pub use macd::{Macd, MacdParams};
// pub use macdrsi::{MacdRsi, MacdRsiParams};
// pub use mamacx::{MAMACX, MAMACXParams};
// pub use rsi::{Rsi, RsiParams};
// pub use single_ma::{SingleMA, SingleMAParams};
// pub use triple_ma::{TripleMA, TripleMAParams};

use crate::{Advice, Candle};
use rand::rngs::StdRng;
use std::cmp::min;

pub trait Strategy {
    type Params;
    fn new(params: &Self::Params) -> Self;
    fn update(&mut self, candle: &Candle) -> Advice;
    fn generate(rng: &mut StdRng) -> Self::Params;
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

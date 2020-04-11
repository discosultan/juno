mod macd;
mod macdrsi;
mod mamacx;
mod rsi;

pub use macd::Macd;
pub use macdrsi::MacdRsi;
pub use mamacx::MAMACX;
pub use rsi::Rsi;
use std::cmp::min;

use crate::{Advice, Candle};

pub trait Strategy {
    fn update(&mut self, candle: &Candle) -> Advice;
}

struct MidTrend {
    ignore: bool,
    previous: Option<Advice>,
}

impl MidTrend {
    pub fn new(ignore: bool) -> Self {
        Self {
            ignore,
            previous: None,
        }
    }

    pub fn maturity(&self) -> u32 {
        1
    }

    pub fn update(&mut self, value: Advice) -> Advice {
        if !self.ignore {
            return value;
        }

        let mut result = Advice::None;
        if self.previous.is_none() {
            self.previous = Some(value)
        } else if Some(value) != self.previous {
            self.ignore = false;
            result = value;
        }
        return result
    }
}

struct Persistence {
    age: u32,
    level: u32,
    potential: Advice,
    previous: Advice,
}

impl Persistence {
    pub fn new(level: u32) -> Self {
        Self {
            age: 0,
            level,
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
        } else {
            self.previous
        };

        self.age = min(self.age + 1, self.level);
        result
    }
}

pub fn combine(advice1: Advice, advice2: Advice) -> Advice {
    if advice1 == Advice::None || advice2 == Advice::None {
        return Advice::None
    }
    // if advice1 != advice2 {
    //     return Advice::Liquidate;
    // }
    advice1
}

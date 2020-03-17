mod macd;
mod macdrsi;
mod mamacx;
mod rsi;

pub use macd::Macd;
pub use macdrsi::MacdRsi;
pub use mamacx::MAMACX;
pub use rsi::Rsi;

use crate::{Advice, Candle};

pub trait Strategy {
    fn update(&mut self, candle: &Candle) -> Option<Advice>;
}

pub struct Persistence {
    age: u32,
    level: u32,
    allow_next: bool,
    value: Option<Advice>,
    potential: Option<Advice>,
    changed: bool,
}

impl Persistence {
    pub fn new(level: u32, allow_initial: bool) -> Self {
        Persistence {
            age: 0,
            level,
            allow_next: allow_initial,
            value: None,
            potential: None,
            changed: false,
        }
    }

    pub fn persisted(&self) -> bool {
        self.value.is_some() && self.age >= self.level
    }

    pub fn update(&mut self, value: Option<Advice>) -> (bool, bool) {
        if value.is_none() || (self.potential.is_some() && value != self.potential) {
            self.allow_next = true;
        }

        if value != self.potential {
            self.age = 0;
            self.potential = value;
        }

        if self.allow_next && self.age == self.level && self.potential != self.value {
            self.value = self.potential;
            self.changed = true;
        } else {
            self.changed = false;
        }

        self.age += 1;

        (self.persisted(), self.changed)
    }
}

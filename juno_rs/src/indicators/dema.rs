use super::{ema::Ema, MA};
use std::cmp::min;

pub struct Dema {
    pub value: f64,
    ema1: Ema,
    ema2: Ema,
    t: u32,
    t1: u32,
    t2: u32,
}

impl Dema {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            ema1: Ema::new(period),
            ema2: Ema::new(period),
            t: 0,
            t1: period,
            t2: (period * 2) - 1,
        }
    }
}

impl MA for Dema {
    fn maturity(&self) -> u32 {
        self.t2
    }

    fn mature(&self) -> bool {
        self.t >= self.t2
    }

    fn update(&mut self, price: f64) {
        self.t = min(self.t + 1, self.t2);

        self.ema1.update(price);

        if self.t <= self.t1 {
            self.ema2.update(price);
        }

        if self.t >= self.t1 {
            self.ema2.update(self.ema1.value);
            if self.mature() {
                self.value = self.ema1.value * 2.0 - self.ema2.value;
            }
        }
    }

    fn value(&self) -> f64 {
        self.value
    }
}

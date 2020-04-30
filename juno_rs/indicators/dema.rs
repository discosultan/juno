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
        let t1 = period - 1;
        Self {
            value: 0.0,
            ema1: Ema::new(period),
            ema2: Ema::new(period),
            t: 0,
            t1,
            t2: t1 * 2,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t2
    }

    pub fn update(&mut self, price: f64) {
        self.ema1.update(price);

        if self.t <= self.t1 {
            self.ema2.update(price);
        }

        if self.t >= self.t1 {
            self.ema2.update(self.ema1.value);
            if self.t == self.t2 {
                self.value = self.ema1.value * 2.0 - self.ema2.value;
            }
        }

        self.t = min(self.t + 1, self.t2);
    }
}

impl MA for Dema {
    fn update(&mut self, price: f64) {
        self.update(price)
    }

    fn value(&self) -> f64 {
        self.value
    }

    fn maturity(&self) -> u32 {
        self.t2
    }
}

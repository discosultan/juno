use super::{sma::Sma, MA};
use std::cmp::min;

pub struct Ema2 {
    pub value: f64,
    pub period: u32,
    a: f64,
    sma: Sma,
    t1: u32,
    t2: u32,
    t: u32,
}

impl Ema2 {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            period,
            a: 2.0 / f64::from(period + 1),
            sma: Sma::new(period),
            t1: period,
            t2: period + 1,
            t: 0,
        }
    }
}

impl MA for Ema2 {
    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, price: f64) {
        if self.t <= self.t1 {
            self.sma.update(price);
        }

        if self.t == self.t1 {
            self.value = self.sma.value
        } else if self.t >= self.t2 {
            self.value = (price - self.value) * self.a + self.value;
        }

        self.t = min(self.t + 1, self.t2)
    }

    fn value(&self) -> f64 {
        self.value
    }
}

use super::{sma::Sma, MA};
use std::cmp::min;

pub struct Smma {
    pub value: f64,

    sma: Sma,
    weight: f64,

    t: u32,
    t1: u32,
    t2: u32,
}

impl Smma {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            sma: Sma::new(period),
            weight: f64::from(period),
            t: 0,
            t1: period,
            t2: period + 1,
        }
    }
}

impl MA for Smma {
    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, price: f64) {
        self.t = min(self.t + 1, self.t2);

        if self.t <= self.t1 {
            self.sma.update(price);
        }

        if self.t == self.t1 {
            self.value = self.sma.value;
        } else if self.t >= self.t2 {
            self.value = (self.value * (self.weight - 1.0) + price) / self.weight;
        }
    }

    fn value(&self) -> f64 {
        self.value
    }
}

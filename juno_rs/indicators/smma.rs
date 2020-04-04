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
            t1: period - 1,
            t2: period,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t1
    }

    pub fn update(&mut self, price: f64) {
        if self.t <= self.t1 {
            self.sma.update(price);
        }

        if self.t == self.t1 {
            self.value = self.sma.value;
        } else {
            self.value = (self.value * (self.weight - 1.0) + price) / self.weight;
        }

        self.t = min(self.t + 1, self.t2);
    }
}

impl MA for Smma {
    fn new(period: u32) -> Self {
        Self::new(period)
    }

    fn update(&mut self, price: f64) {
        self.update(price)
    }

    fn value(&self) -> f64 {
        self.value
    }

    fn maturity(&self) -> u32 {
        self.maturity()
    }
}

use super::{sma::Sma, MA};
use std::cmp::min;

pub struct Ema {
    pub value: f64,
    a: f64,
    t: u32,
    t1: u32,
}

impl Ema {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            a: 2.0 / f64::from(period + 1),
            t: 0,
            t1: period - 1,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t1
    }

    pub fn update(&mut self, price: f64) {
        self.value = match self.t {
            0 => price,
            _ => (price - self.value) * self.a + self.value,
        };
        self.t = min(self.t + 1, self.t1);
    }

    pub fn with_smoothing(period: u32, a: f64) -> Self {
        let mut indicator = Self::new(period);
        indicator.a = a;
        indicator
    }
}

impl MA for Ema {
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
            t1: period - 1,
            t2: period,
            t: 0,
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
            self.value = self.sma.value
        } else if self.t == self.t2 {
            self.value = (price - self.value) * self.a + self.value;
        }

        self.t = min(self.t + 1, self.t2)
    }
}

impl MA for Ema2 {
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

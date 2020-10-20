use super::MA;
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
            t1: period,
        }
    }

    pub fn with_smoothing(period: u32, a: f64) -> Self {
        let mut indicator = Self::new(period);
        indicator.a = a;
        indicator
    }
}

impl MA for Ema {
    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, price: f64) {
        self.t = min(self.t + 1, self.t1);
        self.value = match self.t {
            1 => price,
            _ => (price - self.value) * self.a + self.value,
        };
    }

    fn value(&self) -> f64 {
        self.value
    }
}

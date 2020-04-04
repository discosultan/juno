use super::MA;
use std::cmp::min;

pub struct Sma {
    pub value: f64,
    prices: Vec<f64>,
    i: usize,
    sum: f64,
    t: u32,
    t1: u32,
}

impl Sma {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            prices: vec![0.0; period as usize],
            i: 0,
            sum: 0.0,
            t: 0,
            t1: period - 1,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t1
    }

    pub fn update(&mut self, price: f64) {
        let last = self.prices[self.i];
        self.prices[self.i] = price;
        self.i = (self.i + 1) % self.prices.len();
        self.sum = self.sum - last + price;
        self.value = self.sum / self.prices.len() as f64;

        self.t = min(self.t + 1, self.t1);
    }
}

impl MA for Sma {
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

use super::MA;
use serde::{Deserialize, Serialize};
use std::cmp::min;

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct SmaParams {
    pub period: u32,
}

pub struct Sma {
    pub value: f64,
    prices: Vec<f64>,
    i: usize,
    sum: f64,
    t: u32,
    t1: u32,
}

impl Sma {
    pub fn new(params: &SmaParams) -> Self {
        assert!(params.period > 0);
        Self {
            value: 0.0,
            prices: vec![0.0; params.period as usize],
            i: 0,
            sum: 0.0,
            t: 0,
            t1: params.period,
        }
    }
}

impl MA for Sma {
    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, price: f64) {
        self.t = min(self.t + 1, self.t1);

        let last = self.prices[self.i];
        self.prices[self.i] = price;
        self.i = (self.i + 1) % self.prices.len();
        self.sum = self.sum - last + price;
        self.value = self.sum / self.prices.len() as f64;
    }

    fn value(&self) -> f64 {
        self.value
    }
}

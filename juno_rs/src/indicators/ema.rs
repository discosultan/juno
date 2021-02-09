use super::MA;
use serde::{Deserialize, Serialize};
use std::cmp::min;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct EmaParams {
    pub period: u32,
    pub smoothing: Option<f64>, // Calculated from period if None.
}

pub struct Ema {
    pub value: f64,
    a: f64,
    t: u32,
    t1: u32,
}

impl Ema {
    pub fn new(params: &EmaParams) -> Self {
        assert!(params.period > 0);
        let smoothing = match params.smoothing {
            Some(smoothing) => {
                assert!(0.0 < smoothing && smoothing <= 1.0);
                smoothing
            },
            None => 2.0 / f64::from(params.period + 1),
        };
        Self {
            value: 0.0,
            a: smoothing,
            t: 0,
            t1: params.period,
        }
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

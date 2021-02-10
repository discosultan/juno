use super::MA;
use bounded_vec_deque::BoundedVecDeque;
use serde::{Deserialize, Serialize};
use std::cmp::min;

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
pub struct KamaParams {
    pub period: u32,
}

pub struct Kama {
    pub value: f64,

    short_alpha: f64,
    long_alpha: f64,

    prices: BoundedVecDeque<f64>,
    diffs: BoundedVecDeque<f64>,

    t: u32,
    t1: u32,
    t2: u32,
}

impl Kama {
    pub fn new(params: &KamaParams) -> Self {
        assert!(params.period > 0);
        Self {
            value: 0.0,

            short_alpha: 2.0 / (2.0 + 1.0),
            long_alpha: 2.0 / (30.0 + 1.0),

            prices: BoundedVecDeque::new(params.period as usize),
            diffs: BoundedVecDeque::new(params.period as usize),

            t: 0,
            t1: params.period,
            t2: params.period + 1,
        }
    }
}

impl MA for Kama {
    fn maturity(&self) -> u32 {
        self.t2
    }

    fn mature(&self) -> bool {
        self.t >= self.t2
    }

    fn update(&mut self, price: f64) {
        self.t = min(self.t + 1, self.t2);

        if self.prices.len() > 0 {
            self.diffs
                .push_back(f64::abs(price - self.prices[self.prices.len() - 1]));
        }

        if self.t == self.t1 {
            self.value = price;
        } else if self.t >= self.t2 {
            // TODO: Can optimize this to keep track of sum separately.
            let diff_sum: f64 = self.diffs.iter().sum();
            let er = if diff_sum == 0.0 {
                1.0
            } else {
                f64::abs(price - self.prices[0]) / diff_sum
            };
            let sc = f64::powf(
                er * (self.short_alpha - self.long_alpha) + self.long_alpha,
                2.0,
            );

            self.value += sc * (price - self.value);
        }

        self.prices.push_back(price);
    }

    fn value(&self) -> f64 {
        self.value
    }
}

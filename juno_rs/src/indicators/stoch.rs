use super::{
    sma::{Sma, SmaParams},
    MA,
};
use bounded_vec_deque::BoundedVecDeque;
use std::cmp::min;

pub struct Stoch {
    pub k: f64,
    pub d: f64,
    k_high_window: BoundedVecDeque<f64>,
    k_low_window: BoundedVecDeque<f64>,
    k_sma: Sma,
    d_sma: Sma,
    t: u32,
    t1: u32,
    t2: u32,
    t3: u32,
}

impl Stoch {
    pub fn new(k_period: u32, k_sma_period: u32, d_sma_period: u32) -> Self {
        let t1 = k_period;
        let t2 = t1 + k_sma_period - 1;
        let t3 = t2 + d_sma_period - 1;
        Self {
            k: 0.0,
            d: 0.0,
            k_high_window: BoundedVecDeque::new(k_period as usize),
            k_low_window: BoundedVecDeque::new(k_period as usize),
            k_sma: Sma::new(&SmaParams {
                period: k_sma_period,
            }),
            d_sma: Sma::new(&SmaParams {
                period: d_sma_period,
            }),
            t: 0,
            t1,
            t2,
            t3,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t3
    }

    pub fn mature(&self) -> bool {
        self.t >= self.t3
    }

    pub fn update(&mut self, high: f64, low: f64, close: f64) {
        self.t = min(self.t + 1, self.t3);

        self.k_high_window.push_back(high);
        self.k_low_window.push_back(low);

        if self.t >= self.t1 {
            let max_high = self.k_high_window.iter().cloned().fold(f64::MIN, f64::max);
            let min_low = self.k_low_window.iter().cloned().fold(f64::MAX, f64::min);
            let fast_k = 100.0 * (close - min_low) / (max_high - min_low);

            self.k_sma.update(fast_k);

            if self.t >= self.t2 {
                self.d_sma.update(self.k_sma.value);
            }

            if self.t >= self.t3 {
                self.k = self.k_sma.value;
                self.d = self.d_sma.value;
            }
        }
    }
}

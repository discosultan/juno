use super::MA;
use bounded_vec_deque::BoundedVecDeque;
use std::cmp::min;

pub struct Alma {
    pub value: f64,

    weights: Vec<f64>,
    prices: BoundedVecDeque<f64>,

    t: u32,
    t1: u32,
}

impl Alma {
    pub fn new(period: u32) -> Self {
        let sigma = (period as f64 / 1.5).floor() as u32;
        Self::with_sigma(period, sigma)
    }

    pub fn with_sigma(period: u32, sigma: u32) -> Self {
        let offset = 0.85;

        let m = (offset * (period - 1) as f64).floor();
        let s = period as f64 * 1.0 / sigma as f64;
        let tmp = (0..period)
            .map(|i| (-(i as f64 - m) * (i as f64 - m) / (2.0 * s * s)).exp())
            .collect::<Vec<f64>>();
        let sw: f64 = tmp.iter().sum();
        Self {
            value: 0.0,

            weights: tmp.iter().map(|v| v / sw).collect::<Vec<f64>>(),
            prices: BoundedVecDeque::new(period as usize),

            t: 0,
            t1: period,
        }
    }
}

impl MA for Alma {
    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, price: f64) {
        self.t = min(self.t + 1, self.t1);

        self.prices.push_back(price);

        if self.mature() {
            self.value = self
                .prices
                .iter()
                .zip(self.weights.iter())
                .map(|(p, w)| p * w)
                .sum()
        }
    }

    fn value(&self) -> f64 {
        self.value
    }
}

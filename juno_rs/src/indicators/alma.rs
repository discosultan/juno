use super::MA;
use bounded_vec_deque::BoundedVecDeque;
use serde::{Deserialize, Serialize};
use std::cmp::min;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AlmaParams {
    pub offset: f64, // 0.85
    pub period: u32,
    pub sigma: Option<u32>, // Calculated from period if None.
}

pub struct Alma {
    pub value: f64,

    weights: Vec<f64>,
    prices: BoundedVecDeque<f64>,

    t: u32,
    t1: u32,
}

impl Alma {
    pub fn new(params: &AlmaParams) -> Self {
        assert!(params.period > 0);
        assert!(0.0 < params.offset && params.offset < 1.0);

        let sigma = match params.sigma {
            Some(sigma) => {
                assert!(sigma > 0);
                sigma
            },
            None => (params.period as f64 / 1.5).floor() as u32,
        };

        let m = (params.offset * (params.period - 1) as f64).floor();
        let s = params.period as f64 * 1.0 / sigma as f64;
        let tmp = (0..params.period)
            .map(|i| (-(i as f64 - m) * (i as f64 - m) / (2.0 * s * s)).exp())
            .collect::<Vec<f64>>();
        let sw: f64 = tmp.iter().sum();
        Self {
            value: 0.0,

            weights: tmp.iter().map(|v| v / sw).collect::<Vec<f64>>(),
            prices: BoundedVecDeque::new(params.period as usize),

            t: 0,
            t1: params.period,
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

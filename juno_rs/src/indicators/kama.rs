use bounded_vec_deque::BoundedVecDeque;
use super::MA;
use std::cmp::min;

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
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,

            short_alpha: 2.0 / (2.0 + 1.0),
            long_alpha: 2.0 / (30.0 + 1.0),

            prices: BoundedVecDeque::new(period as usize),
            diffs: BoundedVecDeque::new(period as usize),

            t: 0,
            t1: period,
            t2: period + 1,
        }
    }
}

impl MA for Kama {
    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, price: f64) {
        self.t = min(self.t + 1, self.t2);

        if self.prices.len() > 0 {
            self.diffs.push_back(f64::abs(price - self.prices[self.prices.len() - 1]));
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

#[cfg(test)]
mod tests {
    use super::{super::MA, Kama};

    #[test]
    fn test_kama() {
        let inputs = vec![
            50.25, 50.55, 52.50, 54.50, 54.10, 54.12, 55.50, 50.20, 50.45, 50.24, 50.24, 55.12,
            56.54, 56.12, 56.10, 54.12, 59.54, 54.52,
        ];
        let expected_outputs = vec![
            54.5000, 54.3732, 54.2948, 54.6461, 53.8270, 53.3374, 52.8621, 51.8722, 53.1180,
            54.4669, 55.0451, 55.4099, 55.3468, 55.7115, 55.6875,
        ];
        let mut indicator = Kama::new(4);
        let offset = inputs.len() - expected_outputs.len();
        for i in 0..inputs.len() {
            indicator.update(inputs[i]);
            if i >= offset {
                let value = indicator.value();
                let expected = expected_outputs[i - offset];
                let diff = f64::abs(value - expected);
                assert!(
                    diff < 0.001,
                    format!("expected {} but got {}; diff is {}", expected, value, diff)
                );
            }
        }
    }
}

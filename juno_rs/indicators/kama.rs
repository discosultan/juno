use super::MA;
use std::cmp::min;

pub struct Kama {
    pub value: f64,
    period: u32,

    short_alpha: f64,
    long_alpha: f64,

    prices: Vec<f64>,
    diffs: Vec<f64>,
    i: usize,

    t: u32,
    t1: u32,
    t2: u32,
}

impl Kama {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            period,

            short_alpha: 2.0 / (2.0 + 1.0),
            long_alpha: 2.0 / (30.0 + 1.0),

            prices: vec![0.0; period as usize],
            diffs: vec![0.0; period as usize],
            i: 0,

            t: 0,
            t1: period - 1,
            t2: period,
        }
    }

    pub fn req_history(&self) -> u32 {
        self.t1
    }

    pub fn update(&mut self, price: f64) {
        if self.t > 0 {
            let prev_i = if self.i > 0 {
                self.i - 1
            } else {
                (self.period - 1) as usize
            };
            self.diffs[self.i] = f64::abs(price - self.prices[prev_i]);
        }

        if self.t == self.t1 {
            self.value = price;
        } else if self.t == self.t2 {
            let diff_sum: f64 = self.diffs.iter().sum();
            let er = if diff_sum == 0.0 {
                1.0
            } else {
                let first_i = (self.i + 1) % self.period as usize;
                // if first_i < 0 {
                //     first_i += self.period;
                // }
                f64::abs(price - self.prices[first_i])
            };
            let sc = f64::powf(
                er * (self.short_alpha - self.long_alpha) + self.long_alpha,
                2.0,
            );

            self.value += sc * (price - self.value);
        }

        self.prices[self.i] = price;
        self.i = (self.i + 1) % self.period as usize;
        self.t = min(self.t + 1, self.t2)
    }
}

impl MA for Kama {
    fn new(period: u32) -> Self {
        Self::new(period)
    }

    fn update(&mut self, price: f64) {
        self.update(price)
    }

    fn value(&self) -> f64 {
        self.value
    }

    fn period(&self) -> u32 {
        self.period
    }
}

#[cfg(test)]
mod tests {
    use super::{super::MA, Kama};

    #[test]
    fn test_kama() {
        let inputs = vec![
            50.25, 50.55, 52.5, 54.5, 54.1, 54.12, 55.5, 50.2, 50.45, 50.24, 50.24, 55.12, 56.54,
            56.12, 56.1, 54.12, 59.54, 54.52,
        ];
        let expected_outputs = vec![
            54.5000, 54.3732, 54.2948, 54.6461, 53.8270, 53.3374, 52.8621, 51.8722, 53.1180,
            54.4669, 55.0451, 55.4099, 55.3468, 55.7115, 55.6875,
        ];
        let mut indicator = Kama::new(4);
        for i in 0..inputs.len() {
            indicator.update(inputs[i]);
            if i >= 3 {
                assert_eq!(indicator.value(), expected_outputs[i - 3]);
            }
        }
    }
}

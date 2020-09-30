use super::{smma::Smma, MA};
use std::cmp::min;

pub struct Rsi {
    pub value: f64,

    mean_down: Smma,
    mean_up: Smma,

    last_price: f64,

    t: u32,
    t1: u32,
}

impl Rsi {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            mean_down: Smma::new(period),
            mean_up: Smma::new(period),
            last_price: 0.0,
            t: 0,
            t1: period,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t1
    }

    pub fn mature(&self) -> bool {
        self.t >= self.t1
    }

    pub fn update(&mut self, price: f64) {
        if self.t > 0 {
            let (up, down) = if price > self.last_price {
                (price - self.last_price, 0.0)
            } else if price < self.last_price {
                (0.0, self.last_price - price)
            } else {
                (0.0, 0.0)
            };

            self.mean_up.update(up);
            self.mean_down.update(down);

            if self.t == self.t1 {
                if self.mean_down.value == 0.0 && self.mean_up.value != 0.0 {
                    self.value = 100.0;
                } else if self.mean_down.value == 0.0 {
                    self.value = 0.0;
                } else {
                    let rs = self.mean_up.value / self.mean_down.value;
                    self.value = 100.0 - (100.0 / (1.0 + rs));
                }
            }
        }

        self.last_price = price;
        self.t = min(self.t + 1, self.t1);
    }
}

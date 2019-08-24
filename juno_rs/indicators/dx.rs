use super::di::DI;
use std::cmp::min;

pub struct DX {
    pub value: f64,
    di: DI,
    t: u32,
    t1: u32,
}

impl DX {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            di: DI::new(period),
            t: 0,
            t1: period - 1,
        }
    }

    pub fn update(&mut self, high: f64, low: f64, close: f64) {
        self.di.update(high, low, close);

        self.value = if self.t == self.t1 {
            let dm_diff = (self.di.plus_value - self.di.minus_value).abs();
            let dm_sum = self.di.plus_value + self.di.minus_value;
            dm_diff / dm_sum * 100.0
        } else {
            0.0
        };

        self.t = min(self.t + 1, self.t1);
    }
}

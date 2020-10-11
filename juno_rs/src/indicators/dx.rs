use super::dm::DM;
use std::cmp::min;

pub struct DX {
    pub value: f64,
    dm: DM,
    t: u32,
    t1: u32,
}

impl DX {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            dm: DM::new(period),
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

    pub fn update(&mut self, high: f64, low: f64) {
        self.t = min(self.t + 1, self.t1);

        self.dm.update(high, low);

        if self.t >= self.t1 {
            self.value = self.dm.diff() / self.dm.sum() * 100.0;
        }
    }
}

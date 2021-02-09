use super::{dx::DX, smma::{Smma, SmmaParams}, MA};
use std::cmp::max;

pub struct Adx {
    pub value: f64,
    dx: DX,
    smma: Smma,
}

impl Adx {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            dx: DX::new(period),
            smma: Smma::new(&SmmaParams { period }),
        }
    }

    pub fn maturity(&self) -> u32 {
        max(self.dx.maturity(), self.smma.maturity())
    }

    pub fn mature(&self) -> bool {
        self.dx.mature() && self.smma.mature()
    }

    pub fn update(&mut self, high: f64, low: f64) {
        self.dx.update(high, low);
        self.value = if self.dx.value == 0.0 {
            0.0
        } else {
            self.smma.update(self.dx.value);
            self.smma.value
        }
    }
}

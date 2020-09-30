use super::{dx::DX, smma::Smma, MA};
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
            smma: Smma::new(period),
        }
    }

    pub fn maturity(&self) -> u32 {
        max(self.dx.maturity(), self.smma.maturity())
    }

    pub fn mature(&self) -> bool {
        self.dx.mature() && self.smma.mature()
    }

    pub fn update(&mut self, high: f64, low: f64, close: f64) {
        self.dx.update(high, low, close);
        self.smma.update(self.dx.value);
        self.value = self.smma.value;
    }
}

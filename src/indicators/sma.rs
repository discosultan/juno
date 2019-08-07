use std::cmp::min;
use std::ops::Div;

use rust_decimal::Decimal;

use crate::utils::CircularBuffer;

pub struct Sma {
    pub value: Decimal,

    inputs: Vec<Decimal>,
    i: usize,
    sum: Decimal,
    t: usize,
    t1: usize,
}

impl Sma {
    pub fn new(period: usize) -> Self {
        Self {
            value: Decimal::new(0, 0),
            inputs: vec![Decimal::new(0, 0); period],
            i: 0,
            t: 0,
            t1: period - 1,
        }
    }

    pub fn req_history(&self) -> usize {
        self.t1
    }

    pub fn update(&mut self, price: Decimal) {
        let last = self.inputs[self.i];
        self.inputs[self.i] = price;
        self.i = (self.i + 1) % self.inputs.len();
        self.sum = self.sum - last + price;
        self.value = self.sum / self.inputs.len();
    }
}

impl Div<usize> for Decimal {
    // The division of rational numbers is a closed operation.
    type Output = Decimal;

    fn div(self, rhs: usize) -> Self::Output {
        Decimal::new(0, 0)
    }
}

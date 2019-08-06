use std::cmp::min;

use circular_queue::CircularQueue;
use rust_decimal::Decimal;

use crate::utils::mean;

pub struct Sma {
    pub value: Decimal,
    buffer: CircularQueue<Decimal>,

    t: usize,
    t1: usize,
}

impl Sma {
    pub fn new(period: usize) -> Self {
        Self {
            value: Decimal::new(0, 0),
            buffer: CircularQueue::with_capacity(period),
            t: 0,
            t1: period - 1,
        }
    }

    pub fn req_history(&self) -> usize {
        self.t1
    }

    pub fn update(&mut self, price: Decimal) {
        self.buffer.push(price);
        if self.t == self.t1 {
            self.value = mean(&self.buffer);
        }
        self.t = min(self.t + 1, self.t1);
    }
}

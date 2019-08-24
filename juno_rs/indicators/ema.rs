use std::cmp::min;
use super::sma::Sma;

pub struct Ema {
    pub value: f64,
    a: f64,
    t: u32,
}

impl Ema {
    pub fn new(period: u32) -> Self {
        Self::with_smoothing(2.0 / f64::from(period + 1))
    }

    pub fn req_history(&self) -> u32 {
        0
    }

    pub fn update(&mut self, price: f64) {
        self.value = match self.t {
            0 => {
                self.t = 1;
                price
            }
            _ => (price - self.value) * self.a + self.value,
        };
    }

    pub fn with_smoothing(a: f64) -> Self {
        Self {
            value: 0.0,
            a,
            t: 0,
        }
    }
}

pub struct Ema2 {
    pub value: f64,
    a: f64,
    sma: Sma,
    t1: u32,
    t2: u32,
    t: u32,
}

impl Ema2 {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            a: 2.0 / f64::from(period + 1),
            sma: Sma::new(period),
            t1: period - 1,
            t2: period,
            t: 0,
        }
    }

    pub fn req_history(&self) -> u32 {
        self.t1
    }

    pub fn update(&mut self, price: f64) {
        if self.t <= self.t1 {
            self.sma.update(price);
        }

        if self.t == self.t1 {
            self.value = self.sma.value
        } else if self.t == self.t2 {
            self.value = (price - self.value) * self.a + self.value;
        }

        self.t = min(self.t + 1, self.t2)
    }
}

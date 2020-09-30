use super::dm::DM;
use std::cmp::min;

pub struct DI {
    pub plus_value: f64,
    pub minus_value: f64,
    dm: DM,
    atr: f64,
    per: f64,
    prev_close: f64,
    t: u32,
    t1: u32,
    t2: u32,
    t3: u32,
}

impl DI {
    pub fn new(period: u32) -> Self {
        Self {
            plus_value: 0.0,
            minus_value: 0.0,
            dm: DM::new(period),
            per: f64::from(period - 1) / f64::from(period),
            atr: 0.0,
            prev_close: 0.0,
            t: 0,
            t1: 1,
            t2: period - 1,
            t3: period,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t2
    }

    pub fn mature(&self) -> bool {
        self.t >= self.t2
    }

    pub fn update(&mut self, high: f64, low: f64, close: f64) {
        self.dm.update(high, low);

        if self.t >= self.t1 && self.t < self.t3 {
            self.atr += calc_truerange(self.prev_close, high, low);
        }

        if self.t == self.t2 {
            self.plus_value = 100.0 * self.dm.plus_value / self.atr;
            self.minus_value = 100.0 * self.dm.minus_value / self.atr;
        } else if self.t == self.t3 {
            self.atr = self.atr * self.per + calc_truerange(self.prev_close, high, low);
            self.plus_value = 100.0 * self.dm.plus_value / self.atr;
            self.minus_value = 100.0 * self.dm.minus_value / self.atr;
        }

        self.prev_close = close;
        self.t = min(self.t + 1, self.t3);
    }
}

fn calc_truerange(prev_close: f64, high: f64, low: f64) -> f64 {
    let ych = (high - prev_close).abs();
    let ycl = (low - prev_close).abs();
    let mut v = high - low;
    if ych > v {
        v = ych;
    }
    if ycl > v {
        v = ycl;
    }
    v
}

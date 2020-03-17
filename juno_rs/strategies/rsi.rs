use std::cmp::min;

use crate::{
    indicators,
    strategies::{Persistence, Strategy},
    Advice, Candle,
};

pub struct Rsi {
    rsi: indicators::Rsi,
    up_threshold: f64,
    down_threshold: f64,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Rsi {
    pub fn new(period: u32, up_threshold: f64, down_threshold: f64, persistence: u32) -> Self {
        Self {
            rsi: indicators::Rsi::new(period),
            up_threshold,
            down_threshold,
            persistence: Persistence::new(persistence, false),
            t: 0,
            t1: period - 1,
        }
    }
}

impl Strategy for Rsi {
    fn update(&mut self, candle: &Candle) -> Option<Advice> {
        self.rsi.update(candle.close);

        let mut advice = None;
        if self.t == self.t1 {
            if self.rsi.value < self.down_threshold {
                advice = Some(Advice::Buy);
            } else if self.rsi.value > self.up_threshold {
                advice = Some(Advice::Sell);
            }
        }

        self.t = min(self.t + 1, self.t1);

        let (persisted, _) = self.persistence.update(advice);
        if persisted {
            advice
        } else {
            None
        }
    }
}

use std::cmp::{max, min};

use crate::{
    indicators,
    strategies::{Persistence, Strategy},
    Advice, Candle,
};

pub struct Macd {
    macd: indicators::Macd,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Macd {
    pub fn new(short_period: u32, long_period: u32, signal_period: u32, persistence: u32) -> Self {
        Self {
            macd: indicators::Macd::new(short_period, long_period, signal_period),
            persistence: Persistence::new(persistence, false),
            t: 0,
            t1: max(long_period, signal_period) - 1,
        }
    }
}

impl Strategy for Macd {
    fn update(&mut self, candle: &Candle) -> Option<Advice> {
        self.macd.update(candle.close);

        let mut advice = None;
        if self.t == self.t1 {
            if self.macd.value > self.macd.signal {
                advice = Some(Advice::Buy);
            } else {
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

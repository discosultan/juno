use std::cmp::min;

use crate::{
    indicators,
    strategies::{MidTrend, Persistence, Strategy, combine},
    Advice, Candle,
};

pub struct Rsi {
    rsi: indicators::Rsi,
    up_threshold: f64,
    down_threshold: f64,
    mid_trend: MidTrend,
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
            mid_trend: MidTrend::new(true),
            persistence: Persistence::new(persistence),
            t: 0,
            t1: period - 1,
        }
    }
}

impl Strategy for Rsi {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.rsi.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if self.rsi.value < self.down_threshold {
                advice = Advice::Long;
            } else if self.rsi.value > self.up_threshold {
                advice = Advice::Short;
            }

            advice = combine(
                self.mid_trend.update(advice),
                self.persistence.update(advice),
            );
        }

        self.t = min(self.t + 1, self.t1);
        advice
    }
}

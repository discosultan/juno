use std::cmp::{max, min};

use crate::{
    indicators,
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

pub struct Macd {
    macd: indicators::Macd,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Macd {
    pub fn new(short_period: u32, long_period: u32, signal_period: u32, persistence: u32) -> Self {
        Self {
            macd: indicators::Macd::new(short_period, long_period, signal_period),
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(persistence, false),
            t: 0,
            t1: max(long_period, signal_period) - 1,
        }
    }
}

impl Strategy for Macd {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.macd.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if self.macd.value > self.macd.signal {
                advice = Advice::Long;
            } else {
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

use std::cmp::min;

use crate::{
    indicators::{ma_from_adler32, MA},
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

pub struct DoubleMA {
    short_ma: Box<dyn MA>,
    long_ma: Box<dyn MA>,
    advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl DoubleMA {
    pub fn new(short_ma: u32, long_ma: u32, short_period: u32, long_period: u32) -> Self {
        Self {
            short_ma: ma_from_adler32(short_ma, short_period),
            long_ma: ma_from_adler32(long_ma, long_period),
            advice: Advice::None,
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(0, false),
            t: 0,
            t1: long_period - 1,
        }
    }
}

impl Strategy for DoubleMA {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.short_ma.update(candle.close);
        self.long_ma.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if self.short_ma.value() > self.long_ma.value() {
                self.advice = Advice::Long;
            } else if self.short_ma.value() < self.long_ma.value() {
                self.advice = Advice::Short;
            }

            advice = combine(
                self.mid_trend.update(self.advice),
                self.persistence.update(self.advice),
            );
        }

        self.t = min(self.t + 1, self.t1);
        advice
    }
}

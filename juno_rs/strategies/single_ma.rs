use std::cmp::min;

use crate::{
    indicators::{ma_from_adler32, MA},
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

pub struct SingleMA {
    ma: Box<dyn MA>,
    previous_ma_value: f64,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl SingleMA {
    pub fn new(ma: u32, period: u32, persistence: u32) -> Self {
        Self {
            ma: ma_from_adler32(ma, period),
            previous_ma_value: 0.0,
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(persistence, false),
            t: 0,
            t1: period - 1,
        }
    }
}

impl Strategy for SingleMA {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.ma.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if candle.close > self.ma.value() && self.ma.value() > self.previous_ma_value {
                advice = Advice::Long;
            } else if candle.close < self.ma.value() && self.ma.value() < self.previous_ma_value {
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

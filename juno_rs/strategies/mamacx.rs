use std::cmp::{max, min};

use crate::{
    indicators::{ma_from_adler32, MA},
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

pub struct MAMACX {
    short_ma: Box<dyn MA>,
    long_ma: Box<dyn MA>,
    neg_threshold: f64,
    pos_threshold: f64,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl MAMACX {
    pub fn new(
        short_period: u32,
        long_period: u32,
        neg_threshold: f64,
        pos_threshold: f64,
        persistence: u32,
        short_ma: u32,
        long_ma: u32,
    ) -> Self {
        let short_ma = ma_from_adler32(short_ma, short_period);
        let long_ma = ma_from_adler32(long_ma, long_period);
        let t1 = max(long_ma.maturity(), short_ma.maturity());
        Self {
            short_ma,
            long_ma,
            mid_trend: MidTrend::new(true),
            persistence: Persistence::new(persistence, false),
            neg_threshold,
            pos_threshold,
            t: 0,
            t1,
        }
    }
}

impl Strategy for MAMACX {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.short_ma.update(candle.close);
        self.long_ma.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            let diff = 100.0 * (self.short_ma.value() - self.long_ma.value())
                / ((self.short_ma.value() + self.long_ma.value()) / 2.0);

            if diff > self.pos_threshold {
                advice = Advice::Long;
            } else if diff < self.neg_threshold {
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

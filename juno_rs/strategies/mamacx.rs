use std::cmp::{max, min};

use crate::{
    indicators::MA,
    strategies::{MidTrend, Persistence, Strategy, combine},
    Advice, Candle,
};

pub struct MAMACX<TShort: MA, TLong: MA> {
    short_ma: TShort,
    long_ma: TLong,
    neg_threshold: f64,
    pos_threshold: f64,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl<TShort: MA, TLong: MA> MAMACX<TShort, TLong> {
    pub fn new(
        short_ma: TShort,
        long_ma: TLong,
        neg_threshold: f64,
        pos_threshold: f64,
        persistence: u32,
    ) -> Self {
        let t1 = max(long_ma.maturity(), short_ma.maturity());
        Self {
            short_ma,
            long_ma,
            mid_trend: MidTrend::new(true),
            persistence: Persistence::new(persistence),
            neg_threshold,
            pos_threshold,
            t: 0,
            t1,
        }
    }
}

impl<TShort: MA, TLong: MA> Strategy for MAMACX<TShort, TLong> {
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

use std::cmp::min;

use crate::{
    Advice,
    Candle,
    indicators::MA,
    strategies::{Persistence, Strategy},
};

pub struct MAMACX<TShort: MA, TLong: MA> {
    short_ma: TShort,
    long_ma: TLong,
    neg_threshold: f64,
    pos_threshold: f64,
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
        let long_period = long_ma.period();
        Self {
            short_ma,
            long_ma,
            persistence: Persistence::new(persistence, false),
            neg_threshold,
            pos_threshold,
            t: 0,
            t1: long_period - 1,
        }
    }
}

impl<TShort: MA, TLong: MA> Strategy for MAMACX<TShort, TLong> {
    fn update(&mut self, candle: &Candle) -> Option<Advice> {
        self.short_ma.update(candle.close);
        self.long_ma.update(candle.close);

        let mut advice = None;
        if self.t == self.t1 {
            let diff = 100.0 * (self.short_ma.value() - self.long_ma.value())
                / ((self.short_ma.value() + self.long_ma.value()) / 2.0);

            if diff > self.pos_threshold {
                advice = Some(Advice::Buy);
            } else if diff < self.neg_threshold {
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

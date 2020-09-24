use std::cmp::min;

use crate::{
    indicators::{ma_from_adler32, MA},
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

#[repr(C)]
pub struct TripleMAParams {
    pub short_ma: u32,
    pub medium_ma: u32,
    pub long_ma: u32,
    pub short_period: u32,
    pub medium_period: u32,
    pub long_period: u32,
}

pub struct TripleMA {
    short_ma: Box<dyn MA>,
    medium_ma: Box<dyn MA>,
    long_ma: Box<dyn MA>,
    advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Strategy for TripleMA {
    type Params = TripleMAParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            short_ma: ma_from_adler32(params.short_ma, params.short_period),
            medium_ma: ma_from_adler32(params.medium_ma, params.medium_period),
            long_ma: ma_from_adler32(params.long_ma, params.long_period),
            advice: Advice::None,
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(0, false),
            t: 0,
            t1: params.long_period - 1,
        }
    }

    fn update(&mut self, candle: &Candle) -> Advice {
        self.short_ma.update(candle.close);
        self.medium_ma.update(candle.close);
        self.long_ma.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if self.short_ma.value() > self.medium_ma.value()
                && self.medium_ma.value() > self.long_ma.value()
            {
                self.advice = Advice::Long;
            } else if self.short_ma.value() < self.medium_ma.value()
                && self.medium_ma.value() < self.long_ma.value()
            {
                self.advice = Advice::Short;
            } else if self.advice == Advice::Short
                && self.short_ma.value() > self.medium_ma.value()
                && self.short_ma.value() > self.long_ma.value()
            {
                self.advice = Advice::Liquidate
            } else if self.advice == Advice::Long
                && self.short_ma.value() < self.medium_ma.value()
                && self.short_ma.value() < self.long_ma.value()
            {
                self.advice = Advice::Liquidate;
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
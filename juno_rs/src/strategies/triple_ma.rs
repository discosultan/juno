use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA, MA_CHOICES},
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use std::cmp::min;

#[derive(Chromosome, Clone, Debug)]
#[repr(C)]
pub struct TripleMAParams {
    pub short_ma: u32,
    pub medium_ma: u32,
    pub long_ma: u32,
    pub periods: (u32, u32, u32),
}

fn short_ma(rng: &mut StdRng) -> u32 {
    MA_CHOICES[rng.gen_range(0, MA_CHOICES.len())]
}
fn medium_ma(rng: &mut StdRng) -> u32 {
    MA_CHOICES[rng.gen_range(0, MA_CHOICES.len())]
}
fn long_ma(rng: &mut StdRng) -> u32 {
    MA_CHOICES[rng.gen_range(0, MA_CHOICES.len())]
}
fn periods(rng: &mut StdRng) -> (u32, u32, u32) {
    loop {
        let (s, m, l) = (rng.gen_range(1, 99), rng.gen_range(2, 100), rng.gen_range(3, 101));
        if s < m && m < l {
            return (s, m, l);
        }
    }
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

unsafe impl Send for TripleMA {}
unsafe impl Sync for TripleMA {}

impl Strategy for TripleMA {
    type Params = TripleMAParams;

    fn new(params: &Self::Params) -> Self {
        let (short_period, medium_period, long_period) = params.periods;
        Self {
            short_ma: ma_from_adler32(params.short_ma, short_period),
            medium_ma: ma_from_adler32(params.medium_ma, medium_period),
            long_ma: ma_from_adler32(params.long_ma, long_period),
            advice: Advice::None,
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(0, false),
            t: 0,
            t1: long_period - 1,
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

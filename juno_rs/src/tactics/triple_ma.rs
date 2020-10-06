use super::{Signal, Tactic};
use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA, MA_CHOICES},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;

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
        let (s, m, l) = (
            rng.gen_range(1, 99),
            rng.gen_range(2, 100),
            rng.gen_range(3, 101),
        );
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
}

unsafe impl Send for TripleMA {}
unsafe impl Sync for TripleMA {}

impl Tactic for TripleMA {
    type Params = TripleMAParams;

    fn new(params: &Self::Params) -> Self {
        let (short_period, medium_period, long_period) = params.periods;
        assert!(short_period > 0);
        assert!(short_period < medium_period);
        assert!(medium_period < long_period);

        Self {
            short_ma: ma_from_adler32(params.short_ma, short_period),
            medium_ma: ma_from_adler32(params.medium_ma, medium_period),
            long_ma: ma_from_adler32(params.long_ma, long_period),
            advice: Advice::None,
        }
    }

    fn maturity(&self) -> u32 {
        self.long_ma.maturity()
    }

    fn mature(&self) -> bool {
        self.long_ma.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.short_ma.update(candle.close);
        self.medium_ma.update(candle.close);
        self.long_ma.update(candle.close);

        if self.long_ma.mature() {
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
        }
    }
}

impl Signal for TripleMA {
    fn advice(&self) -> Advice {
        self.advice
    }
}

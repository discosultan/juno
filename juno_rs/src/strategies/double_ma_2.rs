use super::{Signal, StdRngExt, Strategy};
use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::Serialize;
use std::cmp::max;

#[derive(Chromosome, Clone, Debug, Serialize)]
#[repr(C)]
pub struct DoubleMA2Params {
    pub periods: (u32, u32),
    pub neg_threshold: f64,
    pub pos_threshold: f64,
    pub short_ma: u32,
    pub long_ma: u32,
}

fn periods(rng: &mut StdRng) -> (u32, u32) {
    loop {
        let (s, l) = (rng.gen_range(1, 100), rng.gen_range(2, 101));
        if s < l {
            return (s, l);
        }
    }
}
fn neg_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(-1.0, -0.1)
}
fn pos_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.1, 1.0)
}
fn short_ma(rng: &mut StdRng) -> u32 {
    rng.gen_ma()
}
fn long_ma(rng: &mut StdRng) -> u32 {
    rng.gen_ma()
}

#[derive(Signal)]
pub struct DoubleMA2 {
    short_ma: Box<dyn MA>,
    long_ma: Box<dyn MA>,
    neg_threshold: f64,
    pos_threshold: f64,
    advice: Advice,
}

unsafe impl Send for DoubleMA2 {}
unsafe impl Sync for DoubleMA2 {}

impl Strategy for DoubleMA2 {
    type Params = DoubleMA2Params;

    fn new(params: &Self::Params) -> Self {
        let (short_period, long_period) = params.periods;
        assert!(short_period > 0);
        assert!(short_period < long_period);

        let short_ma = ma_from_adler32(params.short_ma, short_period);
        let long_ma = ma_from_adler32(params.long_ma, long_period);
        Self {
            short_ma,
            long_ma,
            neg_threshold: params.neg_threshold,
            pos_threshold: params.pos_threshold,
            advice: Advice::None,
        }
    }

    fn maturity(&self) -> u32 {
        max(self.long_ma.maturity(), self.short_ma.maturity())
    }

    fn mature(&self) -> bool {
        self.long_ma.mature() && self.short_ma.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.short_ma.update(candle.close);
        self.long_ma.update(candle.close);

        if self.mature() {
            let diff = 100.0 * (self.short_ma.value() - self.long_ma.value())
                / ((self.short_ma.value() + self.long_ma.value()) / 2.0);

            if diff > self.pos_threshold {
                self.advice = Advice::Long;
            } else if diff < self.neg_threshold {
                self.advice = Advice::Short;
            }
        }
    }
}

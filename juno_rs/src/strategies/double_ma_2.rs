use super::{Signal, Strategy, StrategyMeta};
use crate::{
    genetics::Chromosome,
    indicators::{MAExt, MAParams, MA},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::max;

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
#[repr(C)]
pub struct DoubleMA2Params {
    pub neg_threshold: f64,
    pub pos_threshold: f64,
    pub mas: (MAParams, MAParams),
}

fn mas(rng: &mut StdRng) -> (MAParams, MAParams) {
    loop {
        let (s, l) = (rng.gen_range(1..200), rng.gen_range(2..201));
        if s < l {
            return (rng.gen_ma_params(s), rng.gen_ma_params(l));
        }
    }
}
fn neg_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(-1.0..-0.1)
}
fn pos_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.1..1.0)
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

    fn new(params: &Self::Params, _meta: &StrategyMeta) -> Self {
        // Non-zero period is validated within indicator.
        let (short_ma, long_ma) = &params.mas;
        assert!(short_ma.period() < long_ma.period());
        assert!(params.pos_threshold > 0.0 && params.pos_threshold < 1.0);
        assert!(params.neg_threshold < 0.0 && params.neg_threshold > -1.0);

        Self {
            short_ma: short_ma.construct(),
            long_ma: long_ma.construct(),
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

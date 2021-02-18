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

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct DoubleMAParams {
    // TODO: Figure out to have these as separate fields!
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

#[derive(Signal)]
pub struct DoubleMA {
    short_ma: Box<dyn MA>,
    long_ma: Box<dyn MA>,
    advice: Advice,
}

unsafe impl Send for DoubleMA {}
unsafe impl Sync for DoubleMA {}

impl DoubleMA {
    pub fn new(params: &DoubleMAParams, _meta: &StrategyMeta) -> Self {
        // Non-zero period is validated within indicator.
        let (short_ma, long_ma) = &params.mas;
        assert!(short_ma.period() < long_ma.period());

        Self {
            short_ma: short_ma.construct(),
            long_ma: long_ma.construct(),
            advice: Advice::None,
        }
    }
}

impl Strategy for DoubleMA {
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
            if self.short_ma.value() > self.long_ma.value() {
                self.advice = Advice::Long;
            } else if self.short_ma.value() < self.long_ma.value() {
                self.advice = Advice::Short;
            }
        }
    }
}

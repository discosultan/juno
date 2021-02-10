use super::{Signal, Strategy, StrategyMeta};
use crate::{
    genetics::Chromosome,
    indicators::{MAParams, StdRngExt, MA},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::max;

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
#[repr(C)]
pub struct TripleMAParams {
    pub mas: (MAParams, MAParams, MAParams),
}

fn mas(rng: &mut StdRng) -> (MAParams, MAParams, MAParams) {
    loop {
        let (s, m, l) = (
            rng.gen_range(1..99),
            rng.gen_range(2..100),
            rng.gen_range(3..101),
        );
        if s < m && m < l {
            return (
                rng.gen_ma_params(s),
                rng.gen_ma_params(m),
                rng.gen_ma_params(l),
            );
        }
    }
}

#[derive(Signal)]
pub struct TripleMA {
    short_ma: Box<dyn MA>,
    medium_ma: Box<dyn MA>,
    long_ma: Box<dyn MA>,
    advice: Advice,
}

unsafe impl Send for TripleMA {}
unsafe impl Sync for TripleMA {}

impl Strategy for TripleMA {
    type Params = TripleMAParams;

    fn new(params: &Self::Params, _meta: &StrategyMeta) -> Self {
        // Non-zero period is validated within indicator.
        let (short_ma, medium_ma, long_ma) = &params.mas;
        assert!(short_ma.period() < medium_ma.period());
        assert!(medium_ma.period() < long_ma.period());

        Self {
            short_ma: short_ma.construct(),
            medium_ma: medium_ma.construct(),
            long_ma: long_ma.construct(),
            advice: Advice::None,
        }
    }

    fn maturity(&self) -> u32 {
        max(
            max(self.long_ma.maturity(), self.medium_ma.maturity()),
            self.short_ma.maturity(),
        )
    }

    fn mature(&self) -> bool {
        self.long_ma.mature() && self.medium_ma.mature() && self.short_ma.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.short_ma.update(candle.close);
        self.medium_ma.update(candle.close);
        self.long_ma.update(candle.close);

        if self.mature() {
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

use super::{Signal, Strategy, StrategyMeta};
use crate::{
    genetics::Chromosome,
    indicators::{self, MAParams, MAExt},
    itertools::IteratorExt,
    Advice, Candle,
};
use bounded_vec_deque::BoundedVecDeque;
use indicators::EmaParams;
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::min;

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
#[repr(C)]
pub struct FourWeekRuleParams {
    pub period: u32,
    pub ma: MAParams,
}

impl Default for FourWeekRuleParams {
    fn default() -> Self {
        Self {
            period: 28,
            ma: MAParams::Ema(EmaParams { period: 14, smoothing: None }),
        }
    }
}

fn period(rng: &mut StdRng) -> u32 {
    rng.gen_range(2..300)
}
fn ma(rng: &mut StdRng) -> MAParams {
    let period = rng.gen_range(2..300);
    rng.gen_ma_params(period)
}

// We can use https://github.com/dtolnay/typetag to serialize a Box<dyn trait> if needed. Otherwise,
// turn it into a generic and use a macro to generate all variations.
#[derive(Signal)]
pub struct FourWeekRule {
    prices: BoundedVecDeque<f64>,
    ma: Box<dyn indicators::MA>,
    advice: Advice,
    t: u32,
    t1: u32,
}

impl Strategy for FourWeekRule {
    type Params = FourWeekRuleParams;

    fn new(params: &Self::Params, _meta: &StrategyMeta) -> Self {
        Self {
            prices: BoundedVecDeque::new(params.period as usize),
            ma: params.ma.construct(),
            advice: Advice::None,
            t: 0,
            t1: params.period + 1,
        }
    }

    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, candle: &Candle) {
        self.t = min(self.t + 1, self.t1);

        self.ma.update(candle.close);

        if self.mature() {
            let (lowest, highest) = self.prices.iter().minmax();

            if candle.close >= highest {
                self.advice = Advice::Long;
            } else if candle.close <= lowest {
                self.advice = Advice::Short;
            } else if (self.advice == Advice::Long && candle.close <= self.ma.value())
                || (self.advice == Advice::Short && candle.close >= self.ma.value())
            {
                self.advice = Advice::Liquidate;
            }
        }

        self.prices.push_back(candle.close);
    }
}

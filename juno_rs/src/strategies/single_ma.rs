use super::{Signal, Strategy, StrategyMeta};
use crate::{
    genetics::Chromosome,
    indicators::{MAParams, MA, MAExt},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::min;

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
#[repr(C)]
pub struct SingleMAParams {
    pub ma: MAParams,
}

fn ma(rng: &mut StdRng) -> MAParams {
    let period = rng.gen_range(1..100);
    rng.gen_ma_params(period)
}

#[derive(Signal)]
pub struct SingleMA {
    ma: Box<dyn MA>,
    previous_ma_value: f64,
    advice: Advice,
    t: u32,
    t1: u32,
}

unsafe impl Send for SingleMA {}
unsafe impl Sync for SingleMA {}

impl Strategy for SingleMA {
    type Params = SingleMAParams;

    fn new(params: &Self::Params, _meta: &StrategyMeta) -> Self {
        let ma = params.ma.construct();
        Self {
            previous_ma_value: 0.0,
            advice: Advice::None,
            t: 0,
            t1: ma.maturity() + 1,
            ma,
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
            if candle.close > self.ma.value() && self.ma.value() > self.previous_ma_value {
                self.advice = Advice::Long;
            } else if candle.close < self.ma.value() && self.ma.value() < self.previous_ma_value {
                self.advice = Advice::Short;
            }
        }

        if self.ma.mature() {
            self.previous_ma_value = self.ma.value();
        }
    }
}

use super::{deserialize_ma, serialize_ma, Signal, StdRngExt, Strategy};
use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::max;

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
#[repr(C)]
pub struct DoubleMAParams {
    #[serde(serialize_with = "serialize_ma")]
    #[serde(deserialize_with = "deserialize_ma")]
    pub short_ma: u32,
    #[serde(serialize_with = "serialize_ma")]
    #[serde(deserialize_with = "deserialize_ma")]
    pub long_ma: u32,
    pub periods: (u32, u32),
}

fn short_ma(rng: &mut StdRng) -> u32 {
    rng.gen_ma()
}
fn long_ma(rng: &mut StdRng) -> u32 {
    rng.gen_ma()
}
fn periods(rng: &mut StdRng) -> (u32, u32) {
    loop {
        let (s, l) = (rng.gen_range(1, 200), rng.gen_range(2, 201));
        if s < l {
            return (s, l);
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

impl Strategy for DoubleMA {
    type Params = DoubleMAParams;

    fn new(params: &Self::Params) -> Self {
        let (short_period, long_period) = params.periods;
        assert!(short_period > 0);
        assert!(short_period < long_period);

        Self {
            short_ma: ma_from_adler32(params.short_ma, short_period),
            long_ma: ma_from_adler32(params.long_ma, long_period),
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
            if self.short_ma.value() > self.long_ma.value() {
                self.advice = Advice::Long;
            } else if self.short_ma.value() < self.long_ma.value() {
                self.advice = Advice::Short;
            }
        }
    }
}

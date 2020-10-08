use super::{Signal, Strategy};
use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA, MA_CHOICES},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;

#[derive(Chromosome, Clone, Debug)]
#[repr(C)]
pub struct SingleMAParams {
    pub ma: u32,
    pub period: u32,
}

fn ma(rng: &mut StdRng) -> u32 {
    MA_CHOICES[rng.gen_range(0, MA_CHOICES.len())]
}
fn period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1, 100)
}

#[derive(Signal)]
pub struct SingleMA {
    ma: Box<dyn MA>,
    previous_ma_value: f64,
    advice: Advice,
}

unsafe impl Send for SingleMA {}
unsafe impl Sync for SingleMA {}

impl Strategy for SingleMA {
    type Params = SingleMAParams;

    fn new(params: &Self::Params) -> Self {
        assert!(params.period > 0);

        Self {
            ma: ma_from_adler32(params.ma, params.period),
            previous_ma_value: 0.0,
            advice: Advice::None,
        }
    }

    fn maturity(&self) -> u32 {
        self.ma.maturity()
    }

    fn mature(&self) -> bool {
        self.ma.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.ma.update(candle.close);

        if self.ma.mature() {
            if candle.close > self.ma.value() && self.ma.value() > self.previous_ma_value {
                self.advice = Advice::Long;
            } else if candle.close < self.ma.value() && self.ma.value() < self.previous_ma_value {
                self.advice = Advice::Short;
            }
        }

        self.previous_ma_value = self.ma.value()
    }
}

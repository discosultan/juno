use super::{Oscillator, Strategy};
use crate::{genetics::Chromosome, indicators, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::Serialize;

#[repr(C)]
#[derive(Chromosome, Clone, Debug, Serialize)]
pub struct RsiParams {
    pub period: u32,
    pub up_threshold: f64,
    pub down_threshold: f64,
}

fn period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1, 101)
}
fn up_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(50.0, 100.0)
}
fn down_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.0, 50.0)
}

pub struct Rsi {
    rsi: indicators::Rsi,
    up_threshold: f64,
    down_threshold: f64,
}

impl Strategy for Rsi {
    type Params = RsiParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            rsi: indicators::Rsi::new(params.period),
            up_threshold: params.up_threshold,
            down_threshold: params.down_threshold,
        }
    }

    fn maturity(&self) -> u32 {
        self.rsi.maturity()
    }

    fn mature(&self) -> bool {
        self.rsi.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.rsi.update(candle.close);
    }
}

impl Oscillator for Rsi {
    fn overbought(&self) -> bool {
        self.rsi.mature() && self.rsi.value >= self.up_threshold
    }

    fn oversold(&self) -> bool {
        self.rsi.mature() && self.rsi.value <= self.down_threshold
    }
}

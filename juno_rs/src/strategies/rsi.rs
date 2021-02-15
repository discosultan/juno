use super::{Oscillator, Strategy, StrategyMeta};
use crate::{genetics::Chromosome, indicators, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct RsiParams {
    pub period: u32,
    pub up_threshold: f64,
    pub down_threshold: f64,
}

fn period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1..101)
}
fn up_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(50.0..100.0)
}
fn down_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.0..50.0)
}

pub struct Rsi {
    indicator: indicators::Rsi,
    up_threshold: f64,
    down_threshold: f64,
}

impl Rsi {
    pub fn new(params: &RsiParams, _meta: &StrategyMeta) -> Self {
        Self {
            indicator: indicators::Rsi::new(params.period),
            up_threshold: params.up_threshold,
            down_threshold: params.down_threshold,
        }
    }
}

impl Strategy for Rsi {
    fn maturity(&self) -> u32 {
        self.indicator.maturity()
    }

    fn mature(&self) -> bool {
        self.indicator.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.indicator.update(candle.close);
    }
}

impl Oscillator for Rsi {
    fn overbought(&self) -> bool {
        self.indicator.mature() && self.indicator.value >= self.up_threshold
    }

    fn oversold(&self) -> bool {
        self.indicator.mature() && self.indicator.value < self.down_threshold
    }
}

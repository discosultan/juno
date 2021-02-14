use super::{Oscillator, Strategy, StrategyMeta};
use crate::{genetics::Chromosome, indicators, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct StochParams {
    pub k_period: u32,
    pub k_sma_period: u32,
    pub d_sma_period: u32,
    pub up_threshold: f64,
    pub down_threshold: f64,
}

fn k_period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1..201)
}
fn k_sma_period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1..201)
}
fn d_sma_period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1..201)
}
fn up_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(50.0..100.0)
}
fn down_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.0..50.0)
}

pub struct Stoch {
    pub indicator: indicators::Stoch,
    up_threshold: f64,
    down_threshold: f64,
}

impl Stoch {
    pub fn new(params: &StochParams, _meta: &StrategyMeta) -> Self {
        Self {
            indicator: indicators::Stoch::new(
                params.k_period,
                params.k_sma_period,
                params.d_sma_period,
            ),
            up_threshold: params.up_threshold,
            down_threshold: params.down_threshold,
        }
    }
}

impl Strategy for Stoch {
    fn maturity(&self) -> u32 {
        self.indicator.maturity()
    }

    fn mature(&self) -> bool {
        self.indicator.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.indicator.update(candle.high, candle.low, candle.close);
    }
}

impl Oscillator for Stoch {
    fn overbought(&self) -> bool {
        self.indicator.mature() && self.indicator.k >= self.up_threshold
    }

    fn oversold(&self) -> bool {
        self.indicator.mature() && self.indicator.k < self.down_threshold
    }
}

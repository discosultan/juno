use crate::{genetics::Chromosome, indicators::Adx, math::lerp, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

pub trait TakeProfit: Send + Sync {
    fn upside_hit(&self) -> bool {
        false
    }

    fn downside_hit(&self) -> bool {
        false
    }

    fn clear(&mut self, _candle: &Candle) {}

    fn update(&mut self, _candle: &Candle) {}
}

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct NoopTakeProfitParams {}

pub struct NoopTakeProfit {}

impl NoopTakeProfit {
    pub fn new(_params: &NoopTakeProfitParams) -> Self {
        Self {}
    }
}

impl TakeProfit for NoopTakeProfit {}

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct BasicTakeProfitParams {
    pub threshold: f64,
}

fn threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.01, 1.0)
}

pub struct BasicTakeProfit {
    pub threshold: f64,
    close_at_position: f64,
    close: f64,
}

impl BasicTakeProfit {
    pub fn new(params: &BasicTakeProfitParams) -> Self {
        Self {
            threshold: params.threshold,
            close_at_position: 0.0,
            close: 0.0,
        }
    }
}

impl TakeProfit for BasicTakeProfit {
    fn upside_hit(&self) -> bool {
        self.close >= self.close_at_position * (1.0 + self.threshold)
    }

    fn downside_hit(&self) -> bool {
        self.close <= self.close_at_position * (1.0 - self.threshold)
    }

    fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
    }
}

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct TrendingTakeProfitParams {
    pub thresholds: (f64, f64),
    pub period: u32,
    pub lock_threshold: bool,
}

fn thresholds(rng: &mut StdRng) -> (f64, f64) {
    loop {
        let (s, l) = (rng.gen_range(0.01, 0.5), rng.gen_range(0.1, 1.0));
        if s < l {
            return (s, l);
        }
    }
}
fn period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1, 100)
}
fn lock_threshold(rng: &mut StdRng) -> bool {
    rng.gen_bool(0.5)
}

pub struct TrendingTakeProfit {
    pub min_threshold: f64,
    pub max_threshold: f64,
    pub lock_threshold: bool,
    threshold: f64,
    adx: Adx,
    close_at_position: f64,
    close: f64,
}

impl TrendingTakeProfit {
    fn get_threshold(&self) -> f64 {
        let adx_value = self.adx.value / 100.0;
        lerp(self.min_threshold, self.max_threshold, adx_value)
    }
}

impl TrendingTakeProfit {
    pub fn new(params: &TrendingTakeProfitParams) -> Self {
        Self {
            min_threshold: params.thresholds.0,
            max_threshold: params.thresholds.1,
            lock_threshold: params.lock_threshold,
            threshold: 0.0,
            adx: Adx::new(params.period),
            close_at_position: 0.0,
            close: 0.0,
        }
    }
}

impl TakeProfit for TrendingTakeProfit {
    fn upside_hit(&self) -> bool {
        self.close >= self.close_at_position * (1.0 + self.threshold)
    }

    fn downside_hit(&self) -> bool {
        self.close <= self.close_at_position * (1.0 - self.threshold)
    }

    fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
        if self.lock_threshold {
            self.threshold = self.get_threshold();
        }
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
        self.adx.update(candle.high, candle.low);
        if !self.lock_threshold {
            self.threshold = self.get_threshold();
        }
    }
}

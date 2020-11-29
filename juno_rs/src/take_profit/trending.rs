use super::TakeProfit;
use crate::{genetics::Chromosome, indicators::Adx, math::lerp, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct TrendingParams {
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

pub struct Trending {
    pub min_threshold: f64,
    pub max_threshold: f64,
    pub lock_threshold: bool,
    threshold: f64,
    adx: Adx,
    close_at_position: f64,
    close: f64,
}

impl Trending {
    fn get_threshold(&self) -> f64 {
        let adx_value = self.adx.value / 100.0;
        lerp(self.min_threshold, self.max_threshold, adx_value)
    }
}

impl TakeProfit for Trending {
    type Params = TrendingParams;

    fn new(params: &Self::Params) -> Self {
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

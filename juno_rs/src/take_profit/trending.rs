use super::TakeProfit;
use crate::{
    easing::{tween, Easing, StdRngExt},
    genetics::Chromosome,
    indicators::Adx,
    math::lerp,
    Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct TrendingParams {
    pub up_thresholds: (f64, f64),
    pub down_thresholds: (f64, f64),
    pub period: u32,
    pub lock_threshold: bool,
    pub easing: Easing,
}

fn up_thresholds(rng: &mut StdRng) -> (f64, f64) {
    loop {
        let (s, l) = (rng.gen_range(0.001..9.999), rng.gen_range(0.002..10.000));
        if s < l {
            return (s, l);
        }
    }
}
fn down_thresholds(rng: &mut StdRng) -> (f64, f64) {
    up_thresholds(rng)
}
fn period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1..200)
}
fn lock_threshold(rng: &mut StdRng) -> bool {
    rng.gen_bool(0.5)
}
fn easing(rng: &mut StdRng) -> Easing {
    rng.gen_easing()
}

pub struct Trending {
    up_min_threshold: f64,
    up_max_threshold: f64,
    down_min_threshold: f64,
    down_max_threshold: f64,
    lock_threshold: bool,
    easing: Easing,
    up_threshold_factor: f64,
    down_threshold_factor: f64,
    adx: Adx,
    close_at_position: f64,
    close: f64,
}

impl Trending {
    fn set_threshold_factors(&mut self) {
        let adx_value = self.adx.value / 100.0;
        let progress = tween(adx_value, self.easing);
        let up_threshold = lerp(self.up_min_threshold, self.up_max_threshold, progress);
        let down_threshold = lerp(self.down_min_threshold, self.down_max_threshold, progress);
        self.up_threshold_factor = 1.0 + up_threshold;
        self.down_threshold_factor = 1.0 - down_threshold;
    }
}

impl TakeProfit for Trending {
    type Params = TrendingParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            up_min_threshold: params.up_thresholds.0,
            up_max_threshold: params.up_thresholds.1,
            down_min_threshold: params.down_thresholds.0,
            down_max_threshold: params.down_thresholds.1,
            lock_threshold: params.lock_threshold,
            easing: params.easing,
            up_threshold_factor: 0.0,
            down_threshold_factor: 0.0,
            adx: Adx::new(params.period),
            close_at_position: 0.0,
            close: 0.0,
        }
    }

    fn upside_hit(&self) -> bool {
        self.close >= self.close_at_position * self.up_threshold_factor
    }

    fn downside_hit(&self) -> bool {
        self.close <= self.close_at_position * self.down_threshold_factor
    }

    fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
        if self.lock_threshold {
            self.set_threshold_factors();
        }
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
        self.adx.update(candle.high, candle.low);
        if !self.lock_threshold {
            self.set_threshold_factors();
        }
    }
}

use super::StopLoss;
use crate::{genetics::Chromosome, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct TrailingParams {
    pub up_threshold: f64,
    pub down_threshold: f64,
}

fn up_threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.001..1.000)
}
fn down_threshold(rng: &mut StdRng) -> f64 {
    up_threshold(rng)
}

pub struct Trailing {
    up_threshold_factor: f64,
    down_threshold_factor: f64,
    highest_close_since_position: f64,
    lowest_close_since_position: f64,
    close: f64,
}

impl Trailing {
    pub fn new(params: &TrailingParams) -> Self {
        Self {
            up_threshold_factor: 1.0 - params.up_threshold,
            down_threshold_factor: 1.0 + params.down_threshold,
            highest_close_since_position: 0.0,
            lowest_close_since_position: f64::MAX,
            close: 0.0,
        }
    }
}

impl StopLoss for Trailing {
    fn upside_hit(&self) -> bool {
        self.close <= self.highest_close_since_position * self.up_threshold_factor
    }

    fn downside_hit(&self) -> bool {
        self.close >= self.lowest_close_since_position * self.down_threshold_factor
    }

    fn clear(&mut self, candle: &Candle) {
        self.highest_close_since_position = candle.close;
        self.lowest_close_since_position = candle.close;
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
        self.highest_close_since_position =
            f64::max(self.highest_close_since_position, candle.close);
        self.lowest_close_since_position = f64::min(self.lowest_close_since_position, candle.close);
    }
}

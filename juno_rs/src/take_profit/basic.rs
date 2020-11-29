use super::TakeProfit;
use crate::{genetics::Chromosome, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct BasicParams {
    pub threshold: f64,
}

fn threshold(rng: &mut StdRng) -> f64 {
    rng.gen_range(0.001, 1.000)
}

pub struct Basic {
    up_threshold_factor: f64,
    down_threshold_factor: f64,
    close_at_position: f64,
    close: f64,
}

impl TakeProfit for Basic {
    type Params = BasicParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            up_threshold_factor: 1.0 + params.threshold,
            down_threshold_factor: 1.0 - params.threshold,
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
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
    }
}

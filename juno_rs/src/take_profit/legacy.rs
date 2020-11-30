use super::TakeProfit;
use crate::{genetics::Chromosome, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct LegacyParams {
    pub threshold: f64,
}

fn threshold(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) {
        rng.gen_range(0.01, 10.00)
    } else {
        0.0
    }
}

pub struct Legacy {
    pub threshold: f64,
    close_at_position: f64,
    close: f64,
}

impl TakeProfit for Legacy {
    type Params = LegacyParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            threshold: params.threshold,
            close_at_position: 0.0,
            close: 0.0,
        }
    }

    fn upside_hit(&self) -> bool {
        self.threshold > 0.0 && self.close >= self.close_at_position * (1.0 + self.threshold)
    }

    fn downside_hit(&self) -> bool {
        self.threshold > 0.0 && self.close <= self.close_at_position * (1.0 - self.threshold)
    }

    fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
    }
}

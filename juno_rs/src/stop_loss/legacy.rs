use super::StopLoss;
use crate::{genetics::Chromosome, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct LegacyParams {
    pub threshold: f64,
    pub trail: bool,
}

fn threshold(rng: &mut StdRng) -> f64 {
    if rng.gen_bool(0.5) {
        rng.gen_range(0.01..1.00)
    } else {
        0.0
    }
}

fn trail(rng: &mut StdRng) -> bool {
    rng.gen_bool(0.5)
}

pub struct Legacy {
    pub threshold: f64,
    trail: bool,
    close_at_position: f64,
    highest_close_since_position: f64,
    lowest_close_since_position: f64,
    close: f64,
}

impl StopLoss for Legacy {
    type Params = LegacyParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            threshold: params.threshold,
            trail: params.trail,
            close_at_position: 0.0,
            highest_close_since_position: 0.0,
            lowest_close_since_position: f64::MAX,
            close: 0.0,
        }
    }

    fn upside_hit(&self) -> bool {
        self.threshold > 0.0
            && self.close
                <= if self.trail {
                    self.highest_close_since_position
                } else {
                    self.close_at_position
                } * (1.0 - self.threshold)
    }

    fn downside_hit(&self) -> bool {
        self.threshold > 0.0
            && self.close
                >= if self.trail {
                    self.lowest_close_since_position
                } else {
                    self.close_at_position
                } * (1.0 + self.threshold)
    }

    fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
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

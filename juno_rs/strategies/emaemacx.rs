use std::cmp::min;

use crate::{Advice, Candle, Trend};
use crate::indicators::Ema;
use crate::strategies::{advice, Strategy};
use crate::utils::Persistence;

pub struct EmaEmaCX {
    ema_short: Ema,
    ema_long: Ema,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl EmaEmaCX {
    pub fn new(
        short_period: u32,
        long_period: u32,
        neg_threshold: f64,
        pos_threshold: f64,
        persistence: u32,
    ) -> Self {
        Self {
            ema_short: Ema::new(short_period),
            ema_long: Ema::new(long_period),
            persistence: Persistence::new(persistence, false),
            neg_threshold,
            pos_threshold,
            t: 0,
            t1: long_period - 1,
        }
    }
}

impl Strategy for EmaEmaCX {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.ema_short.update(candle.close);
        self.ema_long.update(candle.close);

        let mut trend = Trend::Unknown;
        if self.t == self.t1 {
            let diff = 100.0 * (self.ema_short.value - self.ema_long.value)
                / ((self.ema_short.value + self.ema_long.value) / 2.0);

            if diff > self.pos_threshold {
                trend = Trend::Up;
            } else if diff < self.neg_threshold {
                trend = Trend::Down;
            }
        }

        self.t = min(self.t + 1, self.t1);
        
        return advice(self.persistence.update(trend))
    }
}

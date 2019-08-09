use std::cmp::min;

use crate::{Advice, Candle, Trend};
use crate::indicators::Ema;
use crate::strategies::{advice, Strategy};

pub struct Persistence {
    age: u32,
    level: u32,
    allow_next_trend: bool,
    trend: Trend,
    potential_trend: Trend,
}

impl Persistence {
    pub fn new(level: u32, allow_initial_trend: bool) -> Self {
        Persistence {
            age: 0,
            level,
            allow_next_trend: allow_initial_trend,
            trend: Trend::Unknown,
            potential_trend: Trend::Unknown,
        }
    }

    pub fn update(&mut self, trend: Trend) -> (Trend, bool) {
        let mut trend_changed = false;

        if trend == Trend::Unknown ||
            (self.potential_trend != Trend::Unknown && trend != self.potential_trend)
        {
            self.allow_next_trend = true;
        }

        if trend != self.potential_trend {
            self.age = 0;
            self.potential_trend = trend;
        }

        if self.allow_next_trend && self.age == self.level
            && self.potential_trend != self.trend
        {
            self.trend = self.potential_trend;
            trend_changed = true;
        }

        self.age += 1;

        (self.trend, trend_changed)
    }
}

pub struct EmaEmaCx {
    ema_short: Ema,
    ema_long: Ema,
    neg_threshold: f64,
    pos_threshold: f64,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl EmaEmaCx {
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

impl Strategy for EmaEmaCx {
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

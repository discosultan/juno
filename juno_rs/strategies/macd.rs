use std::cmp::{max, min};

use crate::{
    Advice,
    Candle,
    Trend,
    indicators,
    strategies::{advice, Strategy},
    utils::Persistence,
};

pub struct Macd {
    macd: indicators::Macd,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Macd {
    pub fn new(
        short_period: u32,
        long_period: u32,
        signal_period: u32,
        persistence: u32,
    ) -> Self {
        Self {
            macd: indicators::Macd::new(short_period, long_period, signal_period),
            persistence: Persistence::new(persistence, false),
            t: 0,
            t1: max(long_period, signal_period) - 1,
        }
    }
}

impl Strategy for Macd {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.macd.update(candle.close);

        let mut trend = Trend::Unknown;
        if self.t == self.t1 {
            if self.macd.value > self.macd.signal {
                trend = Trend::Up;
            } else {
                trend = Trend::Down;
            }
        }

        self.t = min(self.t + 1, self.t1);

        advice(self.persistence.update(trend))
    }
}

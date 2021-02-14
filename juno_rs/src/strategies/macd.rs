use super::{Signal, Strategy, StrategyMeta};
use crate::{genetics::Chromosome, indicators, Advice, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct MacdParams {
    pub periods: (u32, u32),
    pub signal_period: u32,
}

impl Default for MacdParams {
    fn default() -> Self {
        Self {
            periods: (12, 26),
            signal_period: 9,
        }
    }
}

fn periods(rng: &mut StdRng) -> (u32, u32) {
    loop {
        let (s, l) = (rng.gen_range(1..100), rng.gen_range(2..101));
        if s < l {
            return (s, l);
        }
    }
}
fn signal_period(rng: &mut StdRng) -> u32 {
    rng.gen_range(1..100)
}

#[derive(Signal)]
pub struct Macd {
    macd: indicators::Macd,
    advice: Advice,
}

impl Macd {
    pub fn new(params: &MacdParams, _meta: &StrategyMeta) -> Self {
        let (short_period, long_period) = params.periods;
        Self {
            macd: indicators::Macd::new(short_period, long_period, params.signal_period),
            advice: Advice::None,
        }
    }
}

impl Strategy for Macd {
    fn maturity(&self) -> u32 {
        self.macd.maturity()
    }

    fn mature(&self) -> bool {
        self.macd.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.macd.update(candle.close);

        if self.macd.mature() {
            self.advice = if self.macd.value > self.macd.signal {
                Advice::Long
            } else {
                Advice::Short
            }
        }
    }
}

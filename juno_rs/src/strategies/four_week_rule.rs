use crate::{
    genetics::Chromosome,
    indicators,
    itertools::IteratorExt,
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use std::{cmp::min, collections::VecDeque};
use super::{Signal, Strategy};

#[derive(Chromosome, Clone, Debug)]
#[repr(C)]
pub struct FourWeekRuleParams {
    pub period: u32,
    pub ma: u32,
    pub ma_period: u32,
}

impl Default for FourWeekRuleParams {
    fn default() -> Self {
        Self {
            period: 28,
            ma: indicators::adler32::EMA,
            ma_period: 14,
        }
    }
}

fn period(rng: &mut StdRng) -> u32 {
    rng.gen_range(2, 100)
}
fn ma(rng: &mut StdRng) -> u32 {
    indicators::MA_CHOICES[rng.gen_range(0, indicators::MA_CHOICES.len())]
}
fn ma_period(rng: &mut StdRng) -> u32 {
    rng.gen_range(2, 100)
}

// We can use https://github.com/dtolnay/typetag to serialize a Box<dyn trait> if needed. Otherwise,
// turn it into a generic and use a macro to generate all variations.
#[derive(Signal)]
pub struct FourWeekRule {
    prices: VecDeque<f64>,
    ma: Box<dyn indicators::MA + Send + Sync>,
    advice: Advice,
    t: u32,
    t1: u32,
}

impl Strategy for FourWeekRule {
    type Params = FourWeekRuleParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            prices: VecDeque::with_capacity(params.period as usize),
            ma: indicators::ma_from_adler32(params.ma, params.ma_period),
            advice: Advice::None,
            t: 0,
            t1: params.period,
        }
    }

    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, candle: &Candle) {
        self.ma.update(candle.close);

        if self.mature() {
            let (lowest, highest) = self.prices.iter().minmax();

            if candle.close >= highest {
                self.advice = Advice::Long;
            } else if candle.close <= lowest {
                self.advice = Advice::Short;
            } else if (self.advice == Advice::Long && candle.close <= self.ma.value())
                || (self.advice == Advice::Short && candle.close >= self.ma.value())
            {
                self.advice = Advice::Liquidate;
            }

            self.prices.pop_front();
        }

        self.prices.push_back(candle.close);
        self.t = min(self.t + 1, self.t1);
    }
}

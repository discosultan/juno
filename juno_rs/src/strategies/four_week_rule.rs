use crate::{
    genetics::Chromosome,
    indicators,
    itertools::IteratorExt,
    strategies::{MidTrend, Strategy},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use std::{cmp::min, collections::VecDeque};

#[derive(Chromosome, Clone, Debug)]
#[repr(C)]
pub struct FourWeekRuleParams {
    pub period: u32,
    pub ma: u32,
    pub ma_period: u32,
    pub mid_trend_policy: u32,
}

impl Default for FourWeekRuleParams {
    fn default() -> Self {
        Self {
            period: 28,
            ma: indicators::adler32::EMA,
            ma_period: 14,
            mid_trend_policy: MidTrend::POLICY_IGNORE,
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
fn mid_trend_policy(_rng: &mut StdRng) -> u32 {
    MidTrend::POLICY_IGNORE
}

// We can use https://github.com/dtolnay/typetag to serialize a Box<dyn trait> if needed. Otherwise,
// turn it into a generic and use a macro to generate all variations.
pub struct FourWeekRule {
    mid_trend: MidTrend,
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
            mid_trend: MidTrend::new(params.mid_trend_policy),
            prices: VecDeque::with_capacity(params.period as usize),
            ma: indicators::ma_from_adler32(params.ma, params.ma_period),
            advice: Advice::None,
            t: 0,
            t1: params.period,
        }
    }

    fn update(&mut self, candle: &Candle) -> Advice {
        self.ma.update(candle.close);

        let mut advice = Advice::None;
        if self.t >= self.t1 {
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
            advice = self.mid_trend.update(self.advice);

            self.prices.pop_front();
        }

        self.prices.push_back(candle.close);
        self.t = min(self.t + 1, self.t1);
        advice
    }
}

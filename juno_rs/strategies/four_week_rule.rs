use std::{cmp::min, collections::VecDeque};
use field_count::FieldCount;
use rand::{Rng, rngs::StdRng};
use crate::{
    genetics::Chromosome,
    indicators, math,
    strategies::{MidTrend, Strategy},
    Advice, Candle,
};

#[derive(Clone, FieldCount)]
#[repr(C)]
pub struct FourWeekRuleParams {
    pub period: u32,
    pub ma: u32,
    pub ma_period: u32,
    pub mid_trend_policy: u32,
}

impl Chromosome for FourWeekRuleParams {
    fn generate(rng: &mut StdRng) -> Self {
        Self {
            period: period(rng),
            ma: ma(rng),
            ma_period: ma_period(rng),
            mid_trend_policy: mid_trend_policy(rng),
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        match i {
            0 => self.period = period(rng),
            1 => self.ma = ma(rng),
            2 => self.ma_period = ma_period(rng),
            3 => self.mid_trend_policy = mid_trend_policy(rng),
            _ => panic!("invalid index")
        };
    }

    fn cross(&mut self, parent: &Self, i: usize) {
        match i {
            0 => self.period = parent.period,
            1 => self.ma = parent.ma,
            2 => self.ma_period = parent.ma_period,
            3 => self.mid_trend_policy = parent.mid_trend_policy,
            _ => panic!("invalid index")
        };
    }
}

fn period(rng: &mut StdRng) -> u32 { rng.gen_range(2, 100) }
fn ma(rng: &mut StdRng) -> u32 {
    indicators::MA_CHOICES[rng.gen_range(0, indicators::MA_CHOICES.len())]
}
fn ma_period(rng: &mut StdRng) -> u32 { rng.gen_range(2, 100) }
fn mid_trend_policy(rng: &mut StdRng) -> u32 { MidTrend::POLICY_IGNORE }

pub struct FourWeekRule {
    mid_trend: MidTrend,
    prices: VecDeque<f64>,
    ma: Box<dyn indicators::MA>,
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
            let (lowest, highest) = math::minmax(self.prices.iter());

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

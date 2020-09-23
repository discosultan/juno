use std::{cmp::min, collections::VecDeque};
use field_count::FieldCount;
use rand::{Rng, rngs::StdRng};
use crate::{
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

    fn generate(rng: &mut StdRng) -> Self::Params {
        Self::Params {
            period: rng.gen_range(2, 100),
            ma: indicators::MA_CHOICES[rng.gen_range(0, indicators::MA_CHOICES.len())],
            ma_period: rng.gen_range(2, 100),
            mid_trend_policy: MidTrend::POLICY_IGNORE,
        }
    }
}

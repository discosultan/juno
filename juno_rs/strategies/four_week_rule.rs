use std::{cmp::min, collections::VecDeque};

use crate::{
    indicators, math,
    strategies::{MidTrend, Strategy},
    Advice, Candle,
};

pub struct FourWeekRule {
    mid_trend: MidTrend,
    prices: VecDeque<f64>,
    ma: Box<dyn indicators::MA>,
    advice: Advice,
    t: u32,
    t1: u32,
}

impl FourWeekRule {
    pub fn new(period: u32, ma: u32, ma_period: u32, mid_trend_policy: u32) -> Self {
        Self {
            mid_trend: MidTrend::new(mid_trend_policy),
            prices: VecDeque::with_capacity(period as usize),
            ma: indicators::ma_from_adler32(ma, ma_period),
            advice: Advice::None,
            t: 0,
            t1: period,
        }
    }
}

impl Strategy for FourWeekRule {
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

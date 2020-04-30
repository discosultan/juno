use std::{
    collections::VecDeque,
    cmp::min,
};

use crate::{
    indicators,
    math,
    strategies::Strategy,
    Advice, Candle,
};

pub struct FourWeekRule {
    prices: VecDeque<f64>,
    ma: Box<dyn indicators::MA>,
    advice: Advice,
    t: u32,
}

impl FourWeekRule {
    pub fn new(ma: u32) -> Self {
        Self {
            prices: VecDeque::with_capacity(28),
            ma: indicators::ma_from_adler32(ma, 14),
            advice: Advice::None,
            t: 0,
        }
    }
}

impl Strategy for FourWeekRule {
    fn update(&mut self, candle: &Candle) -> Advice {
        self.ma.update(candle.close);

        if self.t == 28 {
            let (lowest, highest) = math::minmax(self.prices.iter());

            if candle.close >= highest {
                self.advice = Advice::Long;
            } else if candle.close <= lowest {
                self.advice = Advice::Short;
            } else if self.advice == Advice::Long && candle.close <= self.ma.value() {
                self.advice = Advice::Liquidate;
            } else if self.advice == Advice::Short && candle.close >= self.ma.value() {
                self.advice = Advice::Liquidate;
            }

            self.prices.pop_front();
        }

        self.prices.push_back(candle.close);
        self.t = min(self.t + 1, 28);
        self.advice
    }
}

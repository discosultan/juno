use std::cmp::min;

use crate::{
    indicators::{ma_from_adler32, MA},
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

#[repr(C)]
pub struct SingleMAParams {
    pub ma: u32,
    pub period: u32,
    pub persistence: u32,
}

pub struct SingleMA {
    ma: Box<dyn MA>,
    previous_ma_value: f64,
    advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Strategy for SingleMA {
    type Params = SingleMAParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            ma: ma_from_adler32(params.ma, params.period),
            previous_ma_value: 0.0,
            advice: Advice::None,
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(params.persistence, false),
            t: 0,
            t1: params.period - 1,
        }
    }

    fn update(&mut self, candle: &Candle) -> Advice {
        self.ma.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if candle.close > self.ma.value() && self.ma.value() > self.previous_ma_value {
                self.advice = Advice::Long;
            } else if candle.close < self.ma.value() && self.ma.value() < self.previous_ma_value {
                self.advice = Advice::Short;
            }

            advice = combine(
                self.mid_trend.update(self.advice),
                self.persistence.update(self.advice),
            );
        }

        self.previous_ma_value = self.ma.value();
        self.t = min(self.t + 1, self.t1);
        advice
    }
}

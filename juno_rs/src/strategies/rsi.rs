use std::cmp::min;

use crate::{
    indicators,
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

#[repr(C)]
pub struct RsiParams {
    pub period: u32,
    pub up_threshold: f64,
    pub down_threshold: f64,
    pub persistence: u32,
}

pub struct Rsi {
    rsi: indicators::Rsi,
    up_threshold: f64,
    down_threshold: f64,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Strategy for Rsi {
    type Params = RsiParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            rsi: indicators::Rsi::new(params.period),
            up_threshold: params.up_threshold,
            down_threshold: params.down_threshold,
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(params.persistence, false),
            t: 0,
            t1: params.period - 1,
        }
    }

    fn update(&mut self, candle: &Candle) -> Advice {
        self.rsi.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if self.rsi.value < self.down_threshold {
                advice = Advice::Long;
            } else if self.rsi.value > self.up_threshold {
                advice = Advice::Short;
            }

            advice = combine(
                self.mid_trend.update(advice),
                self.persistence.update(advice),
            );
        }

        self.t = min(self.t + 1, self.t1);
        advice
    }
}

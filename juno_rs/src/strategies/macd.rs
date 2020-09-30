use std::cmp::{max, min};

use crate::{
    indicators,
    strategies::{combine, MidTrend, Persistence, Strategy},
    Advice, Candle,
};

#[repr(C)]
pub struct MacdParams {
    pub short_period: u32,
    pub long_period: u32,
    pub signal_period: u32,
    pub persistence: u32,
}

pub struct Macd {
    macd: indicators::Macd,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl Strategy for Macd {
    type Params = MacdParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            macd: indicators::Macd::new(
                params.short_period, params.long_period, params.signal_period
            ),
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(params.persistence, false),
            t: 0,
            t1: max(params.long_period, params.signal_period) - 1,
        }
    }

    fn update(&mut self, candle: &Candle) -> Advice {
        self.macd.update(candle.close);

        let mut advice = Advice::None;
        if self.t == self.t1 {
            if self.macd.value > self.macd.signal {
                advice = Advice::Long;
            } else {
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

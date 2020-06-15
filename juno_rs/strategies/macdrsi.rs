use crate::{
    strategies::{combine, Macd, MidTrend, Persistence, Rsi, Strategy},
    Advice, Candle,
};

pub struct MacdRsi {
    macd: Macd,
    rsi: Rsi,
    mid_trend: MidTrend,
    persistence: Persistence,
}

impl MacdRsi {
    pub fn new(
        macd_short_period: u32,
        macd_long_period: u32,
        macd_signal_period: u32,
        rsi_period: u32,
        rsi_up_threshold: f64,
        rsi_down_threshol: f64,
        persistence: u32,
    ) -> Self {
        Self {
            macd: Macd::new(macd_short_period, macd_long_period, macd_signal_period, 0),
            rsi: Rsi::new(rsi_period, rsi_up_threshold, rsi_down_threshol, 0),
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(persistence, false),
        }
    }
}

impl Strategy for MacdRsi {
    fn update(&mut self, candle: &Candle) -> Advice {
        let macd_advice = self.macd.update(candle);
        let rsi_advice = self.rsi.update(candle);
        let advice = combine(macd_advice, rsi_advice);
        self.persistence.update(advice)
    }
}

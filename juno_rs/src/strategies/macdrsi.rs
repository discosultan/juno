use crate::{
    strategies::{combine, Macd, MacdParams, MidTrend, Persistence, Rsi, RsiParams, Strategy},
    Advice, Candle,
};

#[repr(C)]
pub struct MacdRsiParams {
    pub macd_short_period: u32,
    pub macd_long_period: u32,
    pub macd_signal_period: u32,
    pub rsi_period: u32,
    pub rsi_up_threshold: f64,
    pub rsi_down_threshol: f64,
    pub persistence: u32,
}

pub struct MacdRsi {
    macd: Macd,
    rsi: Rsi,
    mid_trend: MidTrend,
    persistence: Persistence,
}

impl Strategy for MacdRsi {
    type Params = MacdRsiParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            macd: Macd::new(
                &MacdParams {
                    short_period: params.macd_short_period,
                    long_period: params.macd_long_period,
                    signal_period: params.macd_signal_period,
                    persistence: 0,
                }
            ),
            rsi: Rsi::new(
                &RsiParams {
                    period: params.rsi_period,
                    up_threshold: params.rsi_up_threshold,
                    down_threshold: params.rsi_down_threshol,
                    persistence: 0,
                }
            ),
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(params.persistence, false),
        }
    }

    fn update(&mut self, candle: &Candle) -> Advice {
        let macd_advice = self.macd.update(candle);
        let rsi_advice = self.rsi.update(candle);
        let advice = combine(macd_advice, rsi_advice);
        self.persistence.update(advice)
    }
}

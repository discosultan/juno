use crate::{
    Advice,
    Candle,
    strategies::{Persistence, Strategy, Macd, Rsi},
};

pub struct MacdRsi {
    macd: Macd,
    rsi: Rsi,
    persistence: Persistence,
}

fn combine(advice1: Option<Advice>, advice2: Option<Advice>) -> Option<Advice> {
    match (advice1, advice2) {
        (Some(Advice::Buy), Some(Advice::Buy)) => Some(Advice::Buy),
        (Some(Advice::Sell), Some(Advice::Sell)) => Some(Advice::Sell),
        _ => None
    }
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
            persistence: Persistence::new(persistence, false),
        }
    }
}

impl Strategy for MacdRsi {
    fn update(&mut self, candle: &Candle) -> Option<Advice> {
        let macd_advice = self.macd.update(candle);
        let rsi_advice = self.rsi.update(candle);
        let advice = combine(macd_advice, rsi_advice);

        let (persisted, _) = self.persistence.update(advice);
        if persisted {
            advice
        } else {
            None
        }
    }
}

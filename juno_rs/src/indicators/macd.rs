use super::{ema::Ema, MA};
use std::cmp::max;

pub struct Macd {
    pub value: f64,
    pub signal: f64,
    pub histogram: f64,

    short_ema: Ema,
    long_ema: Ema,
    signal_ema: Ema,
}

impl Macd {
    pub fn new(short_period: u32, long_period: u32, signal_period: u32) -> Self {
        // A bit hacky but is what is usually expected.
        let (short_ema, long_ema) = if short_period == 12 && long_period == 26 {
            (
                Ema::with_smoothing(short_period, 0.15),
                Ema::with_smoothing(long_period, 0.075),
            )
        } else {
            (Ema::new(short_period), Ema::new(long_period))
        };
        let signal_ema = Ema::new(signal_period);

        Self {
            value: 0.0,
            signal: 0.0,
            histogram: 0.0,
            short_ema,
            long_ema,
            signal_ema,
        }
    }

    pub fn maturity(&self) -> u32 {
        max(self.long_ema.maturity(), self.short_ema.maturity()) + self.signal_ema.maturity() - 1
    }

    pub fn mature(&self) -> bool {
        self.signal_ema.mature()
    }

    pub fn update(&mut self, price: f64) {
        self.short_ema.update(price);
        self.long_ema.update(price);

        if self.long_ema.mature() && self.short_ema.mature() {
            self.value = self.short_ema.value - self.long_ema.value;
            self.signal_ema.update(self.value);
            self.signal = self.signal_ema.value;
            self.histogram = self.value - self.signal;
        }
    }
}

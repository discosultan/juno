use super::ema::Ema;
use std::cmp::min;

pub struct Macd {
    pub value: f64,
    pub signal: f64,
    pub divergence: f64,

    short_ema: Ema,
    long_ema: Ema,
    signal_ema: Ema,

    t: u32,
    t1: u32,
}

impl Macd {
    pub fn new(short_period: u32, long_period: u32, signal_period: u32) -> Self {
        // A bit hacky but is what is usually expected.
        let (short_ema, long_ema) = if short_period == 12 && long_period == 26 {
            (Ema::with_smoothing(0.15), Ema::with_smoothing(0.075))
        } else {
            (Ema::new(short_period), Ema::new(long_period))
        };
        let signal_ema = Ema::new(signal_period);

        Self {
            signal: 0.0,
            value: 0.0,
            divergence: 0.0,
            short_ema,
            long_ema,
            signal_ema,
            t: 0,
            t1: long_period - 1,
        }
    }

    pub fn req_history(&self) -> u32 {
        self.t1
    }

    pub fn update(&mut self, price: f64) {
        self.short_ema.update(price);
        self.long_ema.update(price);

        if self.t == self.t1 {
            self.value = self.short_ema.value - self.long_ema.value;
            self.signal_ema.update(self.value);
            self.signal = self.signal_ema.value;
            self.divergence = self.value - self.signal;
        }

        self.t = min(self.t + 1, self.t1);
    }
}

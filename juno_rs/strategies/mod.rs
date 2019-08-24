mod emaemacx;

pub use emaemacx::EmaEmaCX;

use crate::{Advice, Candle, Trend};

pub trait Strategy {
    // fn reset(&mut self);

    fn update(&mut self, candle: &Candle) -> Advice;
}

pub fn advice((trend, changed): (Trend, bool)) -> Advice {
    if changed {
        match trend {
            Trend::Up => Advice::Buy,
            Trend::Down => Advice::Sell,
            _ => Advice::None,
        }
    } else {
        Advice::None
    }
}

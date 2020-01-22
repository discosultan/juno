mod macd;
mod mamacx;

pub use macd::Macd;
pub use mamacx::MAMACX;

use crate::{Advice, Candle, Trend};

pub trait Strategy {
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

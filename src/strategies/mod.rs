mod emaemacx;

pub use emaemacx::EmaEmaCx;

use crate::{Advice, Candle, Trend};

pub trait Strategy {
    fn update(&mut self, candle: &Candle) -> Advice;
}

pub fn advice((trend, changed): (Trend, bool)) -> Advice {
    match trend {
        Trend::Up => Advice::Buy,
        Trend::Down => Advice::Sell,
        _ => Advice::None,
    }
}

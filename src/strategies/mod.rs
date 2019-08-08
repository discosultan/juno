mod emaemacx;

pub use emaemacx::EmaEmaCx;

use crate::{Advice, Candle};

pub trait Strategy {
    fn update(&mut self, candle: &Candle) -> Option<Advice>;
}

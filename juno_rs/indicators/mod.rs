mod adx;
mod dema;
mod di;
mod dm;
mod dx;
mod ema;
mod macd;
mod rsi;
mod sma;
mod smma;
mod stoch;

pub use adx::Adx;
pub use dema::Dema;
pub use di::DI;
pub use dm::DM;
pub use dx::DX;
pub use ema::{Ema, Ema2};
pub use macd::Macd;
pub use rsi::Rsi;
pub use sma::Sma;
pub use smma::Smma;
pub use stoch::Stoch;

pub trait MA {
    fn new(period: u32) -> Self;
    fn update(&mut self, price: f64);
    fn value(&self) -> f64;
    fn period(&self) -> u32;
}

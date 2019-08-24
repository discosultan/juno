mod adx;
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
pub use di::DI;
pub use dm::DM;
pub use dx::DX;
pub use ema::{Ema, Ema2};
pub use macd::Macd;
pub use rsi::Rsi;
pub use sma::Sma;
pub use smma::Smma;
pub use stoch::Stoch;

pub trait MovingAverage {
    fn new(period: u32) -> Self;
}
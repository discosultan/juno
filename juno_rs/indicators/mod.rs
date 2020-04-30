mod adx;
mod dema;
mod di;
mod dm;
mod dx;
mod ema;
mod kama;
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
pub use kama::Kama;
pub use macd::Macd;
pub use rsi::Rsi;
pub use sma::Sma;
pub use smma::Smma;
pub use stoch::Stoch;

pub trait MA {
    fn update(&mut self, price: f64);
    fn value(&self) -> f64;
    fn maturity(&self) -> u32;
}

pub fn ma_from_adler32(code: u32, period: u32) -> Box<dyn MA> {
    // Adler32 of lowercased indicator name.
    const EMA: u32 = 40_698_164;
    const EMA2: u32 = 64_160_102;
    const SMA: u32 = 43_450_690;
    const SMMA: u32 = 72_483_247;
    const DEMA: u32 = 66_978_200;
    const KAMA: u32 = 68_026_779;

    match code {
        EMA => Box::new(Ema::new(period)),
        EMA2 => Box::new(Ema2::new(period)),
        SMA => Box::new(Sma::new(period)),
        SMMA => Box::new(Smma::new(period)),
        DEMA => Box::new(Dema::new(period)),
        KAMA => Box::new(Kama::new(period)),
        _ => panic!("indicator not supported"),
    }
}

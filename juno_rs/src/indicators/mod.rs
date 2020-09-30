mod adx;
mod alma;
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
pub use alma::Alma;
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

pub trait MA: Send + Sync {
    fn maturity(&self) -> u32;
    fn mature(&self) -> bool;
    fn update(&mut self, price: f64);
    fn value(&self) -> f64;
}

pub mod adler32 {
    // Adler32 of lowercased indicator name.
    pub const ALMA: u32 = 67_568_028;
    pub const EMA: u32 = 40_698_164;
    pub const EMA2: u32 = 64_160_102;
    pub const SMA: u32 = 43_450_690;
    pub const SMMA: u32 = 72_483_247;
    pub const DEMA: u32 = 66_978_200;
    pub const KAMA: u32 = 68_026_779;
}

pub const MA_CHOICES: [u32; 7] = [
    adler32::ALMA,
    adler32::EMA,
    adler32::EMA2,
    adler32::SMA,
    adler32::SMMA,
    adler32::DEMA,
    adler32::KAMA,
];

pub fn ma_from_adler32(code: u32, period: u32) -> Box<dyn MA + Send + Sync> {
    match code {
        adler32::ALMA => Box::new(Alma::new(period)),
        adler32::EMA => Box::new(Ema::new(period)),
        adler32::EMA2 => Box::new(Ema2::new(period)),
        adler32::SMA => Box::new(Sma::new(period)),
        adler32::SMMA => Box::new(Smma::new(period)),
        adler32::DEMA => Box::new(Dema::new(period)),
        adler32::KAMA => Box::new(Kama::new(period)),
        _ => panic!("indicator not supported"),
    }
}

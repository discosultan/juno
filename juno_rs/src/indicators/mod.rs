mod adx;
mod alma;
mod dema;
mod di;
mod dm;
mod dx;
mod ema;
mod ema2;
mod kama;
mod macd;
mod rsi;
mod sma;
mod smma;
mod stoch;

pub use adx::Adx;
pub use alma::{Alma, AlmaParams};
pub use dema::{Dema, DemaParams};
pub use di::DI;
pub use dm::DM;
pub use dx::DX;
pub use ema::{Ema, EmaParams};
pub use ema2::{Ema2, Ema2Params};
pub use kama::{Kama, KamaParams};
pub use macd::Macd;
pub use rsi::Rsi;
pub use sma::{Sma, SmaParams};
pub use smma::{Smma, SmmaParams};
pub use stoch::Stoch;

use rand::prelude::*;
use serde::{Deserialize, Serialize};

pub trait MA: Send + Sync {
    fn maturity(&self) -> u32;
    fn mature(&self) -> bool;
    fn update(&mut self, price: f64);
    fn value(&self) -> f64;
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(tag = "type")]
pub enum MAParams {
    Alma(AlmaParams),
    Dema(DemaParams),
    Ema(EmaParams),
    Ema2(Ema2Params),
    Kama(KamaParams),
    Sma(SmaParams),
    Smma(SmmaParams),
}

impl MAParams {
    pub fn construct(&self) -> Box<dyn MA> {
        match self {
            MAParams::Sma(params) => Box::new(Sma::new(params)),
            MAParams::Alma(params) => Box::new(Alma::new(params)),
            MAParams::Dema(params) => Box::new(Dema::new(params)),
            MAParams::Ema(params) => Box::new(Ema::new(params)),
            MAParams::Ema2(params) => Box::new(Ema2::new(params)),
            MAParams::Kama(params) => Box::new(Kama::new(params)),
            MAParams::Smma(params) => Box::new(Smma::new(params)),
        }
    }

    pub fn period(&self) -> u32 {
        match self {
            MAParams::Sma(params) => params.period,
            MAParams::Alma(params) => params.period,
            MAParams::Dema(params) => params.period,
            MAParams::Ema(params) => params.period,
            MAParams::Ema2(params) => params.period,
            MAParams::Kama(params) => params.period,
            MAParams::Smma(params) => params.period,
        }
    }
}

pub trait StdRngExt {
    // TODO: remove
    fn gen_ma(&mut self) -> u32;
    fn gen_ma_params(&mut self, period: u32) -> MAParams;
}

impl StdRngExt for StdRng {
    fn gen_ma(&mut self) -> u32 {
        MA_CHOICES[self.gen_range(0..MA_CHOICES.len())]
    }

    fn gen_ma_params(&mut self, period: u32) -> MAParams {
        match self.gen_range(0..7) {
            0 => MAParams::Alma(AlmaParams {
                period,
                offset: 0.85,
                sigma: None,
            }),
            1 => MAParams::Dema(DemaParams { period }),
            2 => MAParams::Ema(EmaParams {
                period,
                smoothing: None,
            }),
            3 => MAParams::Ema2(Ema2Params { period }),
            4 => MAParams::Kama(KamaParams { period }),
            5 => MAParams::Sma(SmaParams { period }),
            6 => MAParams::Smma(SmmaParams { period }),
            _ => panic!(),
        }
    }
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

pub fn ma_from_adler32(code: u32, period: u32) -> Box<dyn MA> {
    match code {
        adler32::ALMA => Box::new(Alma::new(&AlmaParams {
            period,
            offset: 0.85,
            sigma: None,
        })),
        adler32::EMA => Box::new(Ema::new(&EmaParams {
            period,
            smoothing: None,
        })),
        adler32::EMA2 => Box::new(Ema2::new(&Ema2Params { period })),
        adler32::SMA => Box::new(Sma::new(&SmaParams { period })),
        adler32::SMMA => Box::new(Smma::new(&SmmaParams { period })),
        adler32::DEMA => Box::new(Dema::new(&DemaParams { period })),
        adler32::KAMA => Box::new(Kama::new(&KamaParams { period })),
        _ => panic!(format!("indicator {} not supported", code)),
    }
}

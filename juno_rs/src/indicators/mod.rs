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
            Self::Sma(params) => Box::new(Sma::new(params)),
            Self::Alma(params) => Box::new(Alma::new(params)),
            Self::Dema(params) => Box::new(Dema::new(params)),
            Self::Ema(params) => Box::new(Ema::new(params)),
            Self::Ema2(params) => Box::new(Ema2::new(params)),
            Self::Kama(params) => Box::new(Kama::new(params)),
            Self::Smma(params) => Box::new(Smma::new(params)),
        }
    }

    pub fn period(&self) -> u32 {
        match self {
            Self::Sma(params) => params.period,
            Self::Alma(params) => params.period,
            Self::Dema(params) => params.period,
            Self::Ema(params) => params.period,
            Self::Ema2(params) => params.period,
            Self::Kama(params) => params.period,
            Self::Smma(params) => params.period,
        }
    }
}

pub trait MAExt {
    fn gen_ma_params(&mut self, period: u32) -> MAParams;
}

impl MAExt for StdRng {
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

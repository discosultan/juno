mod basic;
mod basic_plus_trailing;
mod legacy;
mod noop;
mod trailing;

pub use basic::{Basic, BasicParams, BasicParamsContext};
pub use basic_plus_trailing::{
    BasicPlusTrailing, BasicPlusTrailingParams, BasicPlusTrailingParamsContext,
};
pub use legacy::{Legacy, LegacyParams, LegacyParamsContext};
pub use noop::{Noop, NoopParams, NoopParamsContext};
pub use trailing::{Trailing, TrailingParams, TrailingParamsContext};

use crate::{genetics::Chromosome, Candle};
use juno_derive_rs::*;
use serde::{Deserialize, Serialize};

pub trait StopLoss: Send + Sync {
    fn upside_hit(&self) -> bool {
        false
    }

    fn downside_hit(&self) -> bool {
        false
    }

    fn clear(&mut self, _candle: &Candle) {}

    fn update(&mut self, _candle: &Candle) {}
}

#[derive(ChromosomeEnum, Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(tag = "type")]
pub enum StopLossParams {
    BasicPlusTrailing(BasicPlusTrailingParams),
    Basic(BasicParams),
    Legacy(LegacyParams),
    Noop(NoopParams),
    Trailing(TrailingParams),
}

impl StopLossParams {
    pub fn construct(&self) -> Box<dyn StopLoss> {
        match self {
            Self::BasicPlusTrailing(params) => Box::new(BasicPlusTrailing::new(params)),
            Self::Basic(params) => Box::new(Basic::new(params)),
            Self::Legacy(params) => Box::new(Legacy::new(params)),
            Self::Noop(params) => Box::new(Noop::new(params)),
            Self::Trailing(params) => Box::new(Trailing::new(params)),
        }
    }
}

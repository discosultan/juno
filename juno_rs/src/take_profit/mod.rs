mod basic;
mod legacy;
mod noop;
mod trending;

pub use basic::{Basic, BasicParams, BasicParamsContext};
pub use legacy::{Legacy, LegacyParams, LegacyParamsContext};
pub use noop::{Noop, NoopParams, NoopParamsContext};
pub use trending::{Trending, TrendingParams, TrendingParamsContext};

use crate::{genetics::Chromosome, Candle};
use juno_derive_rs::*;
use serde::{Deserialize, Serialize};

pub trait TakeProfit: Send + Sync {
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
pub enum TakeProfitParams {
    Basic(BasicParams),
    Legacy(LegacyParams),
    Noop(NoopParams),
    Trending(TrendingParams),
}

impl TakeProfitParams {
    pub fn construct(&self) -> Box<dyn TakeProfit> {
        match self {
            Self::Basic(params) => Box::new(Basic::new(params)),
            Self::Legacy(params) => Box::new(Legacy::new(params)),
            Self::Noop(params) => Box::new(Noop::new(params)),
            Self::Trending(params) => Box::new(Trending::new(params)),
        }
    }
}

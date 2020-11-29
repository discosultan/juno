mod basic;
mod legacy;
mod noop;
mod trending;

pub use basic::{Basic, BasicParams};
pub use legacy::{Legacy, LegacyParams};
pub use noop::{Noop, NoopParams};
pub use trending::{Trending, TrendingParams};

use crate::{genetics::Chromosome, Candle};
use serde::{de::DeserializeOwned, Serialize};

pub trait TakeProfit: Send + Sync {
    type Params: Chromosome + DeserializeOwned + Serialize;

    fn new(params: &Self::Params) -> Self;

    fn upside_hit(&self) -> bool {
        false
    }

    fn downside_hit(&self) -> bool {
        false
    }

    fn clear(&mut self, _candle: &Candle) {}

    fn update(&mut self, _candle: &Candle) {}
}

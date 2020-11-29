mod basic;
mod legacy;
mod noop;
mod trailing;

pub use basic::{Basic, BasicParams};
pub use legacy::{Legacy, LegacyParams};
pub use noop::{Noop, NoopParams};
pub use trailing::{Trailing, TrailingParams};

use crate::{genetics::Chromosome, Candle};
use serde::{de::DeserializeOwned, Serialize};

pub trait StopLoss: Send + Sync {
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

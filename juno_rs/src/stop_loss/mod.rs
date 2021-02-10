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
use rand::prelude::*;
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

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
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
            StopLossParams::BasicPlusTrailing(params) => Box::new(BasicPlusTrailing::new(params)),
            StopLossParams::Basic(params) => Box::new(Basic::new(params)),
            StopLossParams::Legacy(params) => Box::new(Legacy::new(params)),
            StopLossParams::Noop(params) => Box::new(Noop::new(params)),
            StopLossParams::Trailing(params) => Box::new(Trailing::new(params)),
        }
    }
}

pub trait StopLossExt {
    fn gen_stop_loss_params(&mut self) -> StopLossParams;
}

impl StopLossExt for StdRng {
    fn gen_stop_loss_params(&mut self) -> StopLossParams {
        match self.gen_range(0..5) {
            0 => StopLossParams::BasicPlusTrailing(BasicPlusTrailingParams::generate(
                self,
                &BasicPlusTrailingParamsContext::default(),
            )),
            1 => StopLossParams::Basic(BasicParams::generate(self, &BasicParamsContext::default())),
            2 => {
                StopLossParams::Legacy(LegacyParams::generate(self, &LegacyParamsContext::default()))
            }
            3 => StopLossParams::Noop(NoopParams::generate(self, &NoopParamsContext::default())),
            4 => StopLossParams::Trailing(TrailingParams::generate(
                self,
                &TrailingParamsContext::default(),
            )),
            _ => panic!(),
        }
    }
}

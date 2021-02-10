mod basic;
mod legacy;
mod noop;
mod trending;

pub use basic::{Basic, BasicParams, BasicParamsContext};
pub use legacy::{Legacy, LegacyParams, LegacyParamsContext};
pub use noop::{Noop, NoopParams, NoopParamsContext};
pub use trending::{Trending, TrendingParams, TrendingParamsContext};

use crate::{genetics::Chromosome, Candle};
use rand::prelude::*;
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

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
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
            TakeProfitParams::Basic(params) => Box::new(Basic::new(params)),
            TakeProfitParams::Legacy(params) => Box::new(Legacy::new(params)),
            TakeProfitParams::Noop(params) => Box::new(Noop::new(params)),
            TakeProfitParams::Trending(params) => Box::new(Trending::new(params)),
        }
    }
}

pub trait TakeProfitExt {
    fn gen_take_profit_params(&mut self) -> TakeProfitParams;
}

impl TakeProfitExt for StdRng {
    fn gen_take_profit_params(&mut self) -> TakeProfitParams {
        match self.gen_range(0..4) {
            0 => {
                TakeProfitParams::Basic(BasicParams::generate(self, &BasicParamsContext::default()))
            }
            1 => TakeProfitParams::Legacy(LegacyParams::generate(
                self,
                &LegacyParamsContext::default(),
            )),
            2 => TakeProfitParams::Noop(NoopParams::generate(self, &NoopParamsContext::default())),
            3 => TakeProfitParams::Trending(TrendingParams::generate(
                self,
                &TrendingParamsContext::default(),
            )),
            _ => panic!(),
        }
    }
}

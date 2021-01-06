use super::{
    Basic, BasicParams, BasicParamsContext, StopLoss, Trailing, TrailingParams,
    TrailingParamsContext,
};
use crate::{genetics::Chromosome, Candle};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct BasicPlusTrailingParams {
    #[chromosome]
    pub basic: BasicParams,
    #[chromosome]
    pub trailing: TrailingParams,
}

pub struct BasicPlusTrailing {
    basic: Basic,
    trailing: Trailing,
}

impl StopLoss for BasicPlusTrailing {
    type Params = BasicPlusTrailingParams;

    fn new(params: &Self::Params) -> Self {
        Self {
            basic: Basic::new(&params.basic),
            trailing: Trailing::new(&params.trailing),
        }
    }

    fn upside_hit(&self) -> bool {
        self.basic.upside_hit() || self.trailing.upside_hit()
    }

    fn downside_hit(&self) -> bool {
        self.basic.downside_hit() || self.trailing.downside_hit()
    }

    fn clear(&mut self, candle: &Candle) {
        self.basic.clear(candle);
        self.trailing.clear(candle);
    }

    fn update(&mut self, candle: &Candle) {
        self.basic.update(candle);
        self.trailing.update(candle);
    }
}

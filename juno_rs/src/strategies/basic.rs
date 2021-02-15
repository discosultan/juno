use super::{Signal, SignalParams, SignalParamsContext, Strategy, StrategyMeta};
use crate::{genetics::Chromosome, Advice, Candle};
use juno_derive_rs::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct BasicParams {
    #[chromosome]
    pub sig: SignalParams,
}

#[derive(Signal)]
pub struct Basic {
    sig: Box<dyn Signal>,
    advice: Advice,
}

impl Basic {
    pub fn new(params: &BasicParams, meta: &StrategyMeta) -> Self {
        let sig = params.sig.construct(meta);
        Self {
            advice: Advice::None,
            sig,
        }
    }
}

impl Strategy for Basic {
    fn maturity(&self) -> u32 {
        self.sig.maturity()
    }

    fn mature(&self) -> bool {
        self.sig.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.sig.update(candle);
    }
}

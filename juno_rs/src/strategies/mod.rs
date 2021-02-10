mod double_ma;
mod double_ma_2;
mod double_ma_stoch;
mod four_week_rule;
mod macd;
mod rsi;
mod sig;
mod sig_osc;
mod single_ma;
mod stoch;
mod triple_ma;

pub use double_ma::{DoubleMA, DoubleMAParams, DoubleMAParamsContext};
pub use double_ma_2::{DoubleMA2, DoubleMA2Params};
pub use double_ma_stoch::{DoubleMAStoch, DoubleMAStochParams};
pub use four_week_rule::{FourWeekRule, FourWeekRuleParams};
pub use macd::{Macd, MacdParams};
pub use rsi::{Rsi, RsiParams};
pub use sig::{Sig, SigParams};
pub use sig_osc::{SigOsc, SigOscParams};
pub use single_ma::{SingleMA, SingleMAParams};
pub use stoch::{Stoch, StochParams, StochParamsContext};
pub use triple_ma::{TripleMA, TripleMAParams};

use crate::{genetics::Chromosome, Advice, Candle};
use serde::{de::DeserializeOwned, Serialize};

pub struct StrategyMeta {
    pub interval: u64,
}

pub trait Strategy: Send + Sync {
    type Params: Chromosome + DeserializeOwned + Serialize;

    fn new(params: &Self::Params, meta: &StrategyMeta) -> Self;
    fn maturity(&self) -> u32;
    fn mature(&self) -> bool;
    fn update(&mut self, candle: &Candle);
}

pub trait Oscillator: Strategy {
    fn overbought(&self) -> bool;
    fn oversold(&self) -> bool;
}

pub trait Signal: Strategy {
    fn advice(&self) -> Advice;
}

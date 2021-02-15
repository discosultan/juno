mod basic;
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

pub use basic::{Basic, BasicParams, BasicParamsContext};
pub use double_ma::{DoubleMA, DoubleMAParams, DoubleMAParamsContext};
pub use double_ma_2::{DoubleMA2, DoubleMA2Params, DoubleMA2ParamsContext};
pub use double_ma_stoch::{DoubleMAStoch, DoubleMAStochParams, DoubleMAStochParamsContext};
pub use four_week_rule::{FourWeekRule, FourWeekRuleParams, FourWeekRuleParamsContext};
pub use macd::{Macd, MacdParams, MacdParamsContext};
pub use rsi::{Rsi, RsiParams, RsiParamsContext};
pub use sig::{Sig, SigParams, SigParamsContext};
pub use sig_osc::{SigOsc, SigOscParams, SigOscParamsContext};
pub use single_ma::{SingleMA, SingleMAParams, SingleMAParamsContext};
pub use stoch::{Stoch, StochParams, StochParamsContext};
pub use triple_ma::{TripleMA, TripleMAParams, TripleMAParamsContext};

use crate::{genetics::Chromosome, Advice, Candle};
use juno_derive_rs::*;
use serde::{Deserialize, Serialize};

pub struct StrategyMeta {
    pub interval: u64,
}

pub trait Strategy: Send + Sync {
    fn maturity(&self) -> u32;
    fn mature(&self) -> bool;
    fn update(&mut self, candle: &Candle);
}

pub trait Signal: Strategy {
    fn advice(&self) -> Advice;
}

pub trait Oscillator: Strategy {
    fn overbought(&self) -> bool;
    fn oversold(&self) -> bool;
}

#[derive(ChromosomeEnum, Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(tag = "type")]
pub enum StrategyParams {
    Basic(BasicParams),
    SigOsc(SigOscParams),
    Sig(SigParams),
}

impl StrategyParams {
    pub fn construct(&self, meta: &StrategyMeta) -> Box<dyn Signal> {
        match self {
            Self::Basic(params) => Box::new(Basic::new(params, meta)),
            Self::SigOsc(params) => Box::new(SigOsc::new(params, meta)),
            Self::Sig(params) => Box::new(Sig::new(params, meta)),
        }
    }
}

#[derive(ChromosomeEnum, Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(tag = "type")]
pub enum SignalParams {
    DoubleMA(DoubleMAParams),
    DoubleMA2(DoubleMA2Params),
    DoubleMAStoch(DoubleMAStochParams),
    FourWeekRule(FourWeekRuleParams),
    Macd(MacdParams),
    SingleMA(SingleMAParams),
    TripleMA(TripleMAParams),
}

impl SignalParams {
    pub fn construct(&self, meta: &StrategyMeta) -> Box<dyn Signal> {
        match self {
            Self::DoubleMA(params) => Box::new(DoubleMA::new(params, meta)),
            Self::DoubleMA2(params) => Box::new(DoubleMA2::new(params, meta)),
            Self::DoubleMAStoch(params) => Box::new(DoubleMAStoch::new(params, meta)),
            Self::FourWeekRule(params) => Box::new(FourWeekRule::new(params, meta)),
            Self::Macd(params) => Box::new(Macd::new(params, meta)),
            Self::SingleMA(params) => Box::new(SingleMA::new(params, meta)),
            Self::TripleMA(params) => Box::new(TripleMA::new(params, meta)),
        }
    }
}

#[derive(ChromosomeEnum, Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(tag = "type")]
pub enum OscillatorParams {
    Rsi(RsiParams),
    Stoch(StochParams),
}

impl OscillatorParams {
    pub fn construct(&self, meta: &StrategyMeta) -> Box<dyn Oscillator> {
        match self {
            Self::Rsi(params) => Box::new(Rsi::new(params, meta)),
            Self::Stoch(params) => Box::new(Stoch::new(params, meta)),
        }
    }
}

mod sig;
mod sig_osc;
mod double_ma;
mod four_week_rule;
mod macd;
mod rsi;
mod single_ma;
mod triple_ma;

pub use sig::{Cx, CxParams};
pub use sig_osc::{CxOsc, CxOscParams};
pub use double_ma::{DoubleMA, DoubleMA2, DoubleMAParams, DoubleMA2Params};
pub use four_week_rule::{FourWeekRule, FourWeekRuleParams};
pub use macd::{Macd, MacdParams};
pub use rsi::{Rsi, RsiParams};
pub use single_ma::{SingleMA, SingleMAParams};
pub use triple_ma::{TripleMA, TripleMAParams};

use crate::{
    common::{Advice, Candle},
    genetics::Chromosome,
};

// TODO: Rename the trait and module to Strategy / strategies.
pub trait Tactic: Send + Sync {
    type Params: Chromosome;

    fn new(params: &Self::Params) -> Self;
    fn maturity(&self) -> u32;
    fn mature(&self) -> bool;
    fn update(&mut self, candle: &Candle);
}

pub trait Oscillator: Tactic {
    fn overbought(&self) -> bool;
    fn oversold(&self) -> bool;
}

pub trait Signal: Tactic {
    fn advice(&self) -> Advice;
}

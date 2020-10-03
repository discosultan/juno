mod double_ma;
mod rsi;
mod single_ma;
mod triple_ma;

pub use double_ma::{DoubleMA, DoubleMAParams};
pub use rsi::{Rsi, RsiParams};
pub use single_ma::{SingleMA, SingleMAParams};
pub use triple_ma::{TripleMA, TripleMAParams};

use crate::{
    common::{Advice, Candle},
    genetics::Chromosome,
};

pub trait Tactic: Send + Sync {
    type Params: Chromosome;

    fn new(params: &Self::Params) -> Self;
    fn maturity(&self) -> u32;
    fn update(&mut self, candle: &Candle);
}

pub trait Oscillator {
    fn overbought(&self) -> bool;
    fn oversold(&self) -> bool;
}

pub trait Signal {
    fn advice(&self) -> Advice;
}

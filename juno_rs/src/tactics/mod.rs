mod rsi;
mod triple_ma;

pub use rsi::Rsi;
pub use triple_ma::TripleMA;

use crate::{
    common::{Advice, Candle},
    genetics::Chromosome,
};

pub trait Tactic: Send + Sync {
    type Params: Chromosome;

    fn new(params: &Self::Params) -> Self;
    fn update(&mut self, candle: &Candle);
}

pub trait Oscillator {
    fn overbought(&self) -> bool;
    fn oversold(&self) -> bool;
}

pub trait Signal {
    fn advice(&self) -> Advice;
}

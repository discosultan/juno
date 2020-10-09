use super::{Signal, Strategy};
use crate::{
    genetics::Chromosome,
    strategies::{combine, MidTrend, Persistence},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use std::cmp::max;

#[derive(Clone, Debug)]
pub struct SigParams<S: Chromosome> {
    pub sig_params: S,
    pub persistence: u32,
    // TODO: Add midtrendpolicy
}

impl<Sig: Chromosome> Chromosome for SigParams<Sig> {
    fn len() -> usize {
        Sig::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            sig_params: Sig::generate(rng),
            persistence: rng.gen_range(0, 10),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        self.sig_params.cross(&mut other.sig_params, i);
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        self.sig_params.mutate(rng, i);
    }
}

#[derive(Signal)]
pub struct Sig<S: Signal> {
    sig: S,
    mid_trend: MidTrend,
    persistence: Persistence,
    advice: Advice,
}

impl<S: Signal> Strategy for Sig<S> {
    type Params = SigParams<S::Params>;

    fn new(params: &Self::Params) -> Self {
        Self {
            sig: S::new(&params.sig_params),
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(params.persistence, false),
            advice: Advice::None,
        }
    }

    fn maturity(&self) -> u32 {
        self.sig.maturity() + max(self.mid_trend.maturity(), self.persistence.maturity())
    }

    fn mature(&self) -> bool {
        self.sig.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.sig.update(candle);
        if self.sig.mature() {
            self.advice = combine(
                self.mid_trend.update(self.sig.advice()),
                self.persistence.update(self.sig.advice()),
            );
        }
    }
}

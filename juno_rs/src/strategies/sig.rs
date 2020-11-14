use super::{deserialize_mid_trend_policy, serialize_mid_trend_policy, Signal, StdRngExt, Strategy};
use crate::{
    genetics::Chromosome,
    strategies::{combine, MidTrend, Persistence},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::{max, min};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SigParams<S: Chromosome> {
    pub sig_params: S,
    pub persistence: u32,
    #[serde(serialize_with = "serialize_mid_trend_policy")]
    #[serde(deserialize_with = "deserialize_mid_trend_policy")]
    pub mid_trend_policy: u32,
}

impl<Sig: Chromosome> Chromosome for SigParams<Sig> {
    fn len() -> usize {
        Sig::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            sig_params: Sig::generate(rng),
            persistence: rng.gen_range(0, 10),
            mid_trend_policy: rng.gen_mid_trend_policy(),
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
    t: u32,
    t1: u32,
}

impl<S: Signal> Strategy for Sig<S> {
    type Params = SigParams<S::Params>;

    fn new(params: &Self::Params) -> Self {
        let sig = S::new(&params.sig_params);
        let mid_trend = MidTrend::new(params.mid_trend_policy);
        let persistence = Persistence::new(params.persistence, false);
        Self {
            advice: Advice::None,
            t: 0,
            t1: sig.maturity() + max(mid_trend.maturity(), persistence.maturity()) - 1,
            sig,
            mid_trend,
            persistence,
        }
    }

    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, candle: &Candle) {
        self.t = min(self.t + 1, self.t1);

        self.sig.update(candle);
        if self.sig.mature() {
            self.advice = combine(
                self.mid_trend.update(self.sig.advice()),
                self.persistence.update(self.sig.advice()),
            );
        }
    }
}

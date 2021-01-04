use super::{
    deserialize_mid_trend_policy, deserialize_mid_trend_policy_option, serialize_mid_trend_policy,
    serialize_mid_trend_policy_option, Signal, StdRngExt, Strategy,
};
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
    pub sig: S,
    pub persistence: u32,
    #[serde(serialize_with = "serialize_mid_trend_policy")]
    #[serde(deserialize_with = "deserialize_mid_trend_policy")]
    pub mid_trend_policy: u32,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct SigParamsContext<S: Chromosome> {
    pub sig: Option<S::Context>,
    pub persistence: Option<u32>,
    #[serde(serialize_with = "serialize_mid_trend_policy_option")]
    #[serde(deserialize_with = "deserialize_mid_trend_policy_option")]
    pub mid_trend_policy: Option<u32>,
}

impl<Sig: Chromosome> Chromosome for SigParams<Sig> {
    type Context = SigParamsContext<Sig>;

    fn len() -> usize {
        Sig::len() + 2
    }

    fn generate(rng: &mut StdRng, ctx: &Self::Context) -> Self {
        Self {
            sig: Sig::generate(rng, &ctx.sig),
            persistence: ctx.persistence.unwrap_or_else(|| gen_persistence(rng)),
            mid_trend_policy: ctx
                .mid_trend_policy
                .unwrap_or_else(|| rng.gen_mid_trend_policy()),
        }
    }

    fn cross(&mut self, other: &mut Self, mut i: usize) {
        if i < Sig::len() {
            self.sig.cross(&mut other.sig, i);
            return;
        }
        i -= Sig::len();
        match i {
            0 => std::mem::swap(&mut self.persistence, &mut other.persistence),
            1 => std::mem::swap(&mut self.mid_trend_policy, &mut other.mid_trend_policy),
            _ => panic!("index out of bounds"),
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, mut i: usize, ctx: &Self::Context) {
        if i < Sig::len() {
            self.sig.mutate(rng, i, &ctx.sig);
            return;
        }
        i -= Sig::len();
        match i {
            0 => self.persistence = ctx.persistence.unwrap_or_else(|| gen_persistence(rng)),
            1 => {
                self.mid_trend_policy = ctx
                    .mid_trend_policy
                    .unwrap_or_else(|| rng.gen_mid_trend_policy())
            }
            _ => panic!("index out of bounds"),
        }
    }
}

fn gen_persistence(rng: &mut StdRng) -> u32 {
    rng.gen_range(0..10)
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
        let sig = S::new(&params.sig);
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

use super::{Signal, Strategy, StrategyMeta};
use crate::{
    genetics::Chromosome,
    time::{
        deserialize_interval_option, deserialize_interval_option_option, serialize_interval_option,
        serialize_interval_option_option,
    },
    utils::{combine, BufferedCandle, MidTrend, MidTrendPolicy, MidTrendPolicyExt, Persistence},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::{max, min};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct SigParams<S: Chromosome> {
    #[chromosome]
    pub sig: S,
    #[serde(default)]
    pub persistence: u32,
    pub mid_trend_policy: MidTrendPolicy,
    #[serde(default)]
    #[serde(deserialize_with = "deserialize_interval_option")]
    #[serde(serialize_with = "serialize_interval_option")]
    pub buffer_interval: Option<u64>,
}

fn persistence(rng: &mut StdRng) -> u32 {
    rng.gen_range(0..10)
}
fn mid_trend_policy(rng: &mut StdRng) -> MidTrendPolicy {
    rng.gen_mid_trend_policy()
}
fn buffer_interval(_rng: &mut StdRng) -> Option<u64> {
    None
}

#[derive(Signal)]
pub struct Sig<S: Signal> {
    sig: S,
    mid_trend: MidTrend,
    persistence: Persistence,
    buffered_candle: BufferedCandle,
    advice: Advice,
    t: u32,
    t1: u32,
}

impl<S: Signal> Strategy for Sig<S> {
    type Params = SigParams<S::Params>;

    fn new(params: &Self::Params, meta: &StrategyMeta) -> Self {
        let sig = S::new(&params.sig, meta);
        let mid_trend = MidTrend::new(params.mid_trend_policy);
        let persistence = Persistence::new(params.persistence, false);
        Self {
            advice: Advice::None,
            t: 0,
            t1: sig.maturity() + max(mid_trend.maturity(), persistence.maturity()) - 1,
            sig,
            mid_trend,
            persistence,
            buffered_candle: BufferedCandle::new(meta.interval, params.buffer_interval),
        }
    }

    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, candle: &Candle) {
        if let Some(candle) = self.buffered_candle.buffer(candle) {
            self.t = min(self.t + 1, self.t1);

            self.sig.update(candle.as_ref());
            if self.sig.mature() {
                self.advice = combine(
                    self.mid_trend.update(self.sig.advice()),
                    self.persistence.update(self.sig.advice()),
                );
            }
        }
    }
}

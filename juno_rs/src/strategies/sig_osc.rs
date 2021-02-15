use super::{
    Oscillator, OscillatorParams, OscillatorParamsContext, Signal, SignalParams,
    SignalParamsContext, Strategy, StrategyMeta,
};
use crate::{
    genetics::Chromosome,
    utils::{combine, MidTrend, MidTrendPolicy, MidTrendPolicyExt, Persistence},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::{max, min};

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub enum OscFilter {
    Enforce,
    Prevent,
}

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct SigOscParams {
    #[chromosome]
    pub sig: SignalParams,
    #[chromosome]
    pub osc: OscillatorParams,
    pub osc_filter: OscFilter,
    pub persistence: u32,
    pub mid_trend_policy: MidTrendPolicy,
}

fn persistence(rng: &mut StdRng) -> u32 {
    rng.gen_range(0..10)
}
fn mid_trend_policy(rng: &mut StdRng) -> MidTrendPolicy {
    rng.gen_mid_trend_policy()
}
fn osc_filter(rng: &mut StdRng) -> OscFilter {
    if rng.gen_bool(0.5) {
        OscFilter::Enforce
    } else {
        OscFilter::Prevent
    }
}

#[derive(Signal)]
pub struct SigOsc {
    sig: Box<dyn Signal>,
    osc: Box<dyn Oscillator>,
    osc_filter: OscFilter,
    advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl SigOsc {
    pub fn new(params: &SigOscParams, meta: &StrategyMeta) -> Self {
        let sig = params.sig.construct(meta);
        let osc = params.osc.construct(meta);
        let mid_trend = MidTrend::new(params.mid_trend_policy);
        let persistence = Persistence::new(params.persistence, false);
        Self {
            advice: Advice::None,
            t: 0,
            t1: max(sig.maturity(), osc.maturity())
                + max(mid_trend.maturity(), persistence.maturity())
                - 1,
            sig,
            osc,
            osc_filter: params.osc_filter,
            mid_trend,
            persistence,
        }
    }

    fn filter(&self, advice: Advice) -> Advice {
        match self.osc_filter {
            OscFilter::Enforce => self.filter_enforce(advice),
            OscFilter::Prevent => self.filter_prevent(advice),
        }
    }

    fn filter_enforce(&self, advice: Advice) -> Advice {
        match advice {
            Advice::None => Advice::None,
            Advice::Liquidate => Advice::Liquidate,
            Advice::Long => {
                if self.osc.oversold() {
                    Advice::Long
                } else {
                    Advice::Liquidate
                }
            }
            Advice::Short => {
                if self.osc.overbought() {
                    Advice::Short
                } else {
                    Advice::Liquidate
                }
            }
        }
    }

    fn filter_prevent(&self, advice: Advice) -> Advice {
        match advice {
            Advice::None => Advice::None,
            Advice::Liquidate => Advice::Liquidate,
            Advice::Long => {
                if self.osc.overbought() {
                    Advice::Liquidate
                } else {
                    Advice::Long
                }
            }
            Advice::Short => {
                if self.osc.oversold() {
                    Advice::Liquidate
                } else {
                    Advice::Short
                }
            }
        }
    }
}

impl Strategy for SigOsc {
    fn maturity(&self) -> u32 {
        self.t1
    }

    fn mature(&self) -> bool {
        self.t >= self.t1
    }

    fn update(&mut self, candle: &Candle) {
        self.t = min(self.t + 1, self.t1);

        self.sig.update(candle);
        self.osc.update(candle);

        if self.sig.mature() && self.osc.mature() {
            let advice = self.filter(self.sig.advice());
            self.advice = combine(
                self.mid_trend.update(advice),
                self.persistence.update(advice),
            );
        }
    }
}

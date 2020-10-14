use super::{Oscillator, Signal, Strategy};
use crate::{
    genetics::Chromosome,
    strategies::{combine, MidTrend, Persistence},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use std::cmp::{max, min};

#[derive(Clone, Debug)]
pub struct SigOscParams<S: Chromosome, O: Chromosome> {
    pub sig_params: S,
    pub osc_params: O,
    pub persistence: u32,
    pub mid_trend_policy: u32,
}

impl<S: Chromosome, O: Chromosome> Chromosome for SigOscParams<S, O> {
    fn len() -> usize {
        S::len() + O::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            sig_params: S::generate(rng),
            osc_params: O::generate(rng),
            persistence: rng.gen_range(0, 10),
            mid_trend_policy: rng.gen_range(0, MidTrend::POLICIES_LEN),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        if i < S::len() {
            self.sig_params.cross(&mut other.sig_params, i);
        } else {
            self.osc_params.cross(&mut other.osc_params, i - S::len());
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        if i < S::len() {
            self.sig_params.mutate(rng, i);
        } else {
            self.osc_params.mutate(rng, i - S::len());
        }
    }
}

#[derive(Signal)]
pub struct SigOsc<S: Signal, O: Oscillator> {
    sig: S,
    osc: O,
    advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl<S: Signal, O: Oscillator> Strategy for SigOsc<S, O> {
    type Params = SigOscParams<S::Params, O::Params>;

    fn new(params: &Self::Params) -> Self {
        let sig = S::new(&params.sig_params);
        let osc = O::new(&params.osc_params);
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
        self.osc.update(candle);

        if self.sig.mature() && self.osc.mature() {
            let advice = match self.sig.advice() {
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
                    if self.osc.oversold() {
                        Advice::Short
                    } else {
                        Advice::Liquidate
                    }
                }
            };
            self.advice = combine(
                self.mid_trend.update(advice),
                self.persistence.update(advice),
            );
        }
    }
}

use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA, MA_CHOICES},
    strategies::{combine, MidTrend, Persistence},
    Advice, Candle,
};
use rand::prelude::*;
use super::{Signal, Strategy};

#[derive(Clone, Debug)]
pub struct SigParams<S: Chromosome> {
    pub sig_params: S,
}

impl<Sig: Chromosome> Chromosome for SigParams<Sig> {
    fn len() -> usize {
        Sig::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            sig_params: Sig::generate(rng),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        self.sig_params.cross(&mut other.sig_params, i);
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        self.sig_params.mutate(rng, i);
    }
}

pub struct Sig<S: Signal> {
    sig: S,
    // advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    // t: u32,
    // t1: u32,
}

impl<S: Signal> Strategy for Sig<S> {
    type Params = SigParams<S::Params>;

    fn new(params: &Self::Params) -> Self {
        Self {
            sig: S::new(&params.sig_params),
            // short_ma: ma_from_adler32(params.short_ma, short_period),
            // medium_ma: ma_from_adler32(params.medium_ma, medium_period),
            // long_ma: ma_from_adler32(params.long_ma, long_period),
            // advice: Advice::None,
            mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            persistence: Persistence::new(0, false),
            // t: 0,
            // t1: long_period - 1,
        }
    }

    fn maturity(&self) -> u32 {
        self.sig.maturity()
    }

    fn mature(&self) -> bool {
        self.sig.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.sig.update(candle);
        // Advice::None

        // let mut advice = Advice::None;
        // if self.t == self.t1 {
        //     if self.short_ma.value() > self.medium_ma.value()
        //         && self.medium_ma.value() > self.long_ma.value()
        //     {
        //         self.advice = Advice::Long;
        //     } else if self.short_ma.value() < self.medium_ma.value()
        //         && self.medium_ma.value() < self.long_ma.value()
        //     {
        //         self.advice = Advice::Short;
        //     } else if self.advice == Advice::Short
        //         && self.short_ma.value() > self.medium_ma.value()
        //         && self.short_ma.value() > self.long_ma.value()
        //     {
        //         self.advice = Advice::Liquidate
        //     } else if self.advice == Advice::Long
        //         && self.short_ma.value() < self.medium_ma.value()
        //         && self.short_ma.value() < self.long_ma.value()
        //     {
        //         self.advice = Advice::Liquidate;
        //     }

        //     advice = combine(
        //         self.mid_trend.update(self.advice),
        //         self.persistence.update(self.advice),
        //     );
        // }

        // self.t = min(self.t + 1, self.t1);
        // advice
    }
}

impl<S: Signal> Signal for Sig<S> {
    fn advice(&self) -> Advice {
        self.sig.advice()
    }
}


use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA, MA_CHOICES},
    strategies::{combine, MidTrend, Persistence},
    tactics::{Oscillator, Signal, Tactic},
    Advice, Candle,
};
use rand::prelude::*;

#[derive(Clone, Debug)]
pub struct CxParams<C: Chromosome> {
    pub cx_params: C,
}

impl<C: Chromosome> Chromosome for CxParams<C> {
    fn len() -> usize {
        C::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            cx_params: C::generate(rng),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        self.cx_params.cross(&mut other.cx_params, i);
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        self.cx_params.mutate(rng, i);
    }
}

pub struct Cx<C: Signal> {
    cx: C,
    // short_ma: Box<dyn MA>,
    // medium_ma: Box<dyn MA>,
    // long_ma: Box<dyn MA>,
    // advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    // t: u32,
    // t1: u32,
}

// unsafe impl Send for CxOsc {}
// unsafe impl Sync for CxOsc {}

impl<C: Signal> Tactic for Cx<C> {
    type Params = CxParams<C::Params>;

    fn new(params: &Self::Params) -> Self {
        Self {
            cx: C::new(&params.cx_params),
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
        self.cx.maturity()
    }

    fn mature(&self) -> bool {
        self.cx.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.cx.update(candle);
        // Advice::None
        // self.short_ma.update(candle.close);
        // self.medium_ma.update(candle.close);
        // self.long_ma.update(candle.close);

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

impl<C: Signal> Signal for Cx<C> {
    fn advice(&self) -> Advice {
        self.cx.advice()
    }
}


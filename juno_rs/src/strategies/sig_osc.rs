use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA, MA_CHOICES},
    strategies::{combine, MidTrend, Persistence},
    Advice, Candle,
};
use rand::prelude::*;
use std::cmp::max;
use super::{Oscillator, Signal, Strategy};

#[derive(Clone, Debug)]
pub struct SigOscParams<C: Chromosome, O: Chromosome> {
    pub cx_params: C,
    pub osc_params: O,
}

impl<S: Chromosome, O: Chromosome> Chromosome for SigOscParams<S, O> {
    fn len() -> usize {
        S::len() + O::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            cx_params: S::generate(rng),
            osc_params: O::generate(rng),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        if i < S::len() {
            self.cx_params.cross(&mut other.cx_params, i);
        } else {
            self.osc_params.cross(&mut other.osc_params, i - S::len());
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        if i < S::len() {
            self.cx_params.mutate(rng, i);
        } else {
            self.osc_params.mutate(rng, i - S::len());
        }
    }
}

pub struct SigOsc<C: Signal, O: Oscillator> {
    cx: C,
    osc: O,
    // short_ma: Box<dyn MA>,
    // medium_ma: Box<dyn MA>,
    // long_ma: Box<dyn MA>,
    // advice: Advice,
    // mid_trend: MidTrend,
    // persistence: Persistence,
    // t: u32,
    // t1: u32,
}

// unsafe impl Send for CxOsc {}
// unsafe impl Sync for CxOsc {}

impl<S: Signal, O: Oscillator> Strategy for SigOsc<S, O> {
    type Params = SigOscParams<S::Params, O::Params>;

    fn new(params: &Self::Params) -> Self {
        Self {
            cx: S::new(&params.cx_params),
            osc: O::new(&params.osc_params),
            // short_ma: ma_from_adler32(params.short_ma, short_period),
            // medium_ma: ma_from_adler32(params.medium_ma, medium_period),
            // long_ma: ma_from_adler32(params.long_ma, long_period),
            // advice: Advice::None,
            // mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
            // persistence: Persistence::new(0, false),
            // t: 0,
            // t1: long_period - 1,
        }
    }

    fn maturity(&self) -> u32 {
        max(self.cx.maturity(), self.osc.maturity())
    }

    fn mature(&self) -> bool {
        self.cx.mature() && self.osc.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.cx.update(candle);
        self.osc.update(candle);

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

impl<S: Signal, O: Oscillator> Signal for SigOsc<S, O> {
    fn advice(&self) -> Advice {
        if self.mature() {
            match self.cx.advice() {
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
            }
        } else {
            Advice::None
        }
    }
}

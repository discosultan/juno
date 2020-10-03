use crate::{
    genetics::Chromosome,
    indicators::{ma_from_adler32, MA, MA_CHOICES},
    strategies::{combine, MidTrend, Persistence, Strategy},
    tactics::{Oscillator, Signal, Tactic},
    Advice, Candle,
};
use rand::prelude::*;
use std::cmp::min;

#[derive(Clone, Debug)]
pub struct CxOscParams<C: Chromosome, O: Chromosome> {
    pub cx_params: C,
    pub osc_params: O,
}

impl<C: Chromosome, O: Chromosome> Chromosome for CxOscParams<C, O> {
    fn len() -> usize {
        C::len() + O::len()
    }

    fn generate(rng: &mut StdRng) -> Self {
        Self {
            cx_params: C::generate(rng),
            osc_params: O::generate(rng),
        }
    }

    fn cross(&mut self, other: &mut Self, i: usize) {
        if i < C::len() {
            self.cx_params.cross(&mut other.cx_params, i);
        } else {
            self.osc_params.cross(&mut other.osc_params, i - C::len());
        }
    }

    fn mutate(&mut self, rng: &mut StdRng, i: usize) {
        if i < C::len() {
            self.cx_params.mutate(rng, i);
        } else {
            self.osc_params.mutate(rng, i - C::len());
        }
    }
}

pub struct CxOsc<C: Tactic + Signal, O: Tactic + Oscillator> {
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

impl<C: Tactic + Signal, O: Tactic + Oscillator> Strategy for CxOsc<C, O> {
    type Params = CxOscParams<C::Params, O::Params>;

    fn new(params: &Self::Params) -> Self {
        Self {
            cx: C::new(&params.cx_params),
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

    fn update(&mut self, candle: &Candle) -> Advice {
        self.cx.update(candle);
        self.osc.update(candle);

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

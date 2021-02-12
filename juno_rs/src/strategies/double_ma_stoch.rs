use super::{Oscillator, Signal, Strategy, StrategyMeta};
use crate::{
    genetics::Chromosome,
    strategies::{
        DoubleMA, DoubleMAParams, DoubleMAParamsContext, Stoch, StochParams, StochParamsContext,
    },
    Advice, Candle,
};
use juno_derive_rs::*;
use serde::{Deserialize, Serialize};
use std::cmp::max;

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct DoubleMAStochParams {
    #[chromosome]
    pub double_ma: DoubleMAParams,
    #[chromosome]
    pub stoch: StochParams,
}

#[derive(Signal)]
pub struct DoubleMAStoch {
    double_ma: DoubleMA,
    stoch: Stoch,
    advice: Advice,
}

impl Strategy for DoubleMAStoch {
    type Params = DoubleMAStochParams;

    fn new(params: &Self::Params, meta: &StrategyMeta) -> Self {
        Self {
            double_ma: DoubleMA::new(&params.double_ma, meta),
            stoch: Stoch::new(&params.stoch, meta),
            advice: Advice::None,
        }
    }

    fn maturity(&self) -> u32 {
        max(self.double_ma.maturity(), self.stoch.maturity())
    }

    fn mature(&self) -> bool {
        self.double_ma.mature() && self.stoch.mature()
    }

    fn update(&mut self, candle: &Candle) {
        self.double_ma.update(candle);
        self.stoch.update(candle);

        if self.mature() {
            // TODO: Try adding changed filter to MA output?
            let ma_advice = self.double_ma.advice();

            // Exit conditions.
            if self.advice == Advice::Long
                && (ma_advice == Advice::Short || self.stoch.overbought())
            {
                self.advice = Advice::Liquidate
            } else if self.advice == Advice::Short
                && (ma_advice == Advice::Long || self.stoch.oversold())
            {
                self.advice = Advice::Liquidate;
            }

            // Entry conditions.
            if self.advice != Advice::Long && self.advice != Advice::Short {
                if ma_advice == Advice::Long && self.stoch.indicator.k < 50.0 {
                    self.advice = Advice::Long;
                } else if ma_advice == Advice::Short && self.stoch.indicator.k >= 50.0 {
                    self.advice = Advice::Short;
                }
            }
        }
    }
}

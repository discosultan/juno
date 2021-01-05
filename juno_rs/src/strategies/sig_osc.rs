use super::{
    deserialize_mid_trend_policy, deserialize_mid_trend_policy_option, serialize_mid_trend_policy,
    serialize_mid_trend_policy_option, Oscillator, Signal, StdRngExt, Strategy,
};
use crate::{
    genetics::Chromosome,
    strategies::{combine, MidTrend, Persistence},
    Advice, Candle,
};
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::cmp::{max, min};

const OSC_FILTER_ENFORCE: u32 = 0;
const OSC_FILTER_PREVENT: u32 = 1;

fn osc_filter_to_str(value: u32) -> &'static str {
    match value {
        OSC_FILTER_ENFORCE => "enforce",
        OSC_FILTER_PREVENT => "prevent",
        _ => panic!("unknown osc filter value: {}", value),
    }
}

fn str_to_osc_filter(representation: &str) -> u32 {
    match representation {
        "enforce" => OSC_FILTER_ENFORCE,
        "prevent" => OSC_FILTER_PREVENT,
        _ => panic!(
            "unknown osc filter representation: {}",
            representation
        ),
    }
}

fn serialize_osc_filter<S>(value: &u32, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    serializer.serialize_str(osc_filter_to_str(*value))
}

fn deserialize_osc_filter<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(str_to_osc_filter(Deserialize::deserialize(deserializer)?))
}

pub fn serialize_osc_filter_option<S>(value: &Option<u32>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    match value {
        Some(value) => serializer.serialize_str(osc_filter_to_str(*value)),
        None => serializer.serialize_none(),
    }
}

pub fn deserialize_osc_filter_option<'de, D>(deserializer: D) -> Result<Option<u32>, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: Option<&str> = Deserialize::deserialize(deserializer)?;
    Ok(representation.map(|repr| str_to_osc_filter(repr)))
}

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct SigOscParams<S: Chromosome, O: Chromosome> {
    #[chromosome]
    pub sig: S,
    #[chromosome]
    pub osc: O,
    #[serde(serialize_with = "serialize_osc_filter")]
    #[serde(deserialize_with = "deserialize_osc_filter")]
    pub osc_filter: u32,
    pub persistence: u32,
    #[serde(serialize_with = "serialize_mid_trend_policy")]
    #[serde(deserialize_with = "deserialize_mid_trend_policy")]
    pub mid_trend_policy: u32,
}

fn persistence(rng: &mut StdRng) -> u32 {
    rng.gen_range(0..10)
}
fn mid_trend_policy(rng: &mut StdRng) -> u32 {
    rng.gen_mid_trend_policy()
}
fn osc_filter(rng: &mut StdRng) -> u32 {
    if rng.gen_bool(0.5) {
        OSC_FILTER_ENFORCE
    } else {
        OSC_FILTER_PREVENT
    }
}

// #[derive(Debug, Deserialize, Serialize)]
// pub struct SigOscParamsContext<S: Chromosome, O: Chromosome> {
//     pub sig: Option<S>,
//     pub osc: Option<O>,
//     #[serde(serialize_with = "serialize_osc_filter_option")]
//     #[serde(deserialize_with = "deserialize_osc_filter_option")]
//     pub osc_filter: Option<u32>,
//     pub persistence: Option<u32>,
//     #[serde(serialize_with = "serialize_mid_trend_policy_option")]
//     #[serde(deserialize_with = "deserialize_mid_trend_policy_option")]
//     pub mid_trend_policy: Option<u32>,
// }

#[derive(Signal)]
pub struct SigOsc<S: Signal, O: Oscillator> {
    sig: S,
    osc: O,
    osc_filter: u32,
    advice: Advice,
    mid_trend: MidTrend,
    persistence: Persistence,
    t: u32,
    t1: u32,
}

impl<S: Signal, O: Oscillator> SigOsc<S, O> {
    fn filter(&self, advice: Advice) -> Advice {
        match self.osc_filter {
            OSC_FILTER_ENFORCE => self.filter_enforce(advice),
            OSC_FILTER_PREVENT => self.filter_prevent(advice),
            _ => panic!("Invalid osc_filter: {}", self.osc_filter),
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

impl<S: Signal, O: Oscillator> Strategy for SigOsc<S, O> {
    type Params = SigOscParams<S::Params, O::Params>;

    fn new(params: &Self::Params) -> Self {
        let sig = S::new(&params.sig);
        let osc = O::new(&params.osc);
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

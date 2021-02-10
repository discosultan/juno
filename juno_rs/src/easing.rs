use once_cell::sync::Lazy;
use rand::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

pub fn tween(x: f64, easing: Easing) -> f64 {
    (EASINGS[&easing])(x)
}

fn linear(x: f64) -> f64 {
    x
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
pub enum Easing {
    Linear,
    QuadIn,
    QuadOut,
    QuadInout,
    CubicIn,
    CubicOut,
    CubicInout,
    QuartIn,
    QuartOut,
    QuartInout,
    QuintIn,
    QuintOut,
    QuintInout,
    SineIn,
    SineOut,
    SineInout,
    CircIn,
    CircOut,
    CircInout,
    ExpoIn,
    ExpoOut,
    ExpoInout,
    ElasticIn,
    ElasticOut,
    ElasticInout,
    BackIn,
    BackOut,
    BackInout,
    BounceIn,
    BounceOut,
    BounceInout,
}

static EASINGS: Lazy<HashMap<Easing, fn(f64) -> f64>> = Lazy::new(|| {
    [
        (Easing::Linear, linear as fn(f64) -> f64),
        (Easing::QuadIn, ezing::quad_in::<f64> as fn(f64) -> f64),
        (Easing::QuadOut, ezing::quad_out::<f64>),
        (Easing::QuadInout, ezing::quad_inout::<f64>),
        (Easing::CubicIn, ezing::cubic_in::<f64>),
        (Easing::CubicOut, ezing::cubic_out::<f64>),
        (Easing::CubicInout, ezing::cubic_inout::<f64>),
        (Easing::QuartIn, ezing::quart_in::<f64>),
        (Easing::QuartOut, ezing::quart_out::<f64>),
        (Easing::QuartInout, ezing::quart_inout::<f64>),
        (Easing::QuintIn, ezing::quint_in::<f64>),
        (Easing::QuintOut, ezing::quint_out::<f64>),
        (Easing::QuintInout, ezing::quint_inout::<f64>),
        (Easing::SineIn, ezing::sine_in::<f64>),
        (Easing::SineOut, ezing::sine_out::<f64>),
        (Easing::SineInout, ezing::sine_inout::<f64>),
        (Easing::CircIn, ezing::circ_in::<f64>),
        (Easing::CircOut, ezing::circ_out::<f64>),
        (Easing::CircInout, ezing::circ_inout::<f64>),
        (Easing::ExpoIn, ezing::expo_in::<f64>),
        (Easing::ExpoOut, ezing::expo_out::<f64>),
        (Easing::ExpoInout, ezing::expo_inout::<f64>),
        (Easing::ElasticIn, ezing::elastic_in::<f64>),
        (Easing::ElasticOut, ezing::elastic_out::<f64>),
        (Easing::ElasticInout, ezing::elastic_inout::<f64>),
        (Easing::BackIn, ezing::back_in::<f64>),
        (Easing::BackOut, ezing::back_out::<f64>),
        (Easing::BackInout, ezing::back_inout::<f64>),
        (Easing::BounceIn, ezing::bounce_in::<f64>),
        (Easing::BounceOut, ezing::bounce_out::<f64>),
        (Easing::BounceInout, ezing::bounce_inout::<f64>),
    ]
    .iter()
    .cloned()
    .collect()
});

static EASING_CHOICES: Lazy<Vec<Easing>> = Lazy::new(|| EASINGS.keys().map(|&k| k).collect());

pub trait EasingExt {
    fn gen_easing(&mut self) -> Easing;
}

impl EasingExt for StdRng {
    fn gen_easing(&mut self) -> Easing {
        *EASING_CHOICES.choose(self).unwrap()
    }
}

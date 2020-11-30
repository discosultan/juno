use ezing;
use once_cell::sync::Lazy;
use rand::prelude::*;
use serde::{Deserialize, Deserializer, Serializer};
use std::collections::HashMap;

pub fn tween(x: f64, easing: u32) -> f64 {
    (EASINGS[&easing])(x)
}

fn linear(x: f64) -> f64 {
    x
}

pub const EASING_LINEAR: u32 = 0;
pub const EASING_QUAD_IN: u32 = 1;
pub const EASING_QUAD_OUT: u32 = 2;
pub const EASING_QUAD_INOUT: u32 = 3;
pub const EASING_CUBIC_IN: u32 = 4;
pub const EASING_CUBIC_OUT: u32 = 5;
pub const EASING_CUBIC_INOUT: u32 = 6;
pub const EASING_QUART_IN: u32 = 7;
pub const EASING_QUART_OUT: u32 = 8;
pub const EASING_QUART_INOUT: u32 = 9;
pub const EASING_QUINT_IN: u32 = 10;
pub const EASING_QUINT_OUT: u32 = 11;
pub const EASING_QUINT_INOUT: u32 = 12;
pub const EASING_SINE_IN: u32 = 13;
pub const EASING_SINE_OUT: u32 = 14;
pub const EASING_SINE_INOUT: u32 = 15;
pub const EASING_CIRC_IN: u32 = 16;
pub const EASING_CIRC_OUT: u32 = 17;
pub const EASING_CIRC_INOUT: u32 = 18;
pub const EASING_EXPO_IN: u32 = 19;
pub const EASING_EXPO_OUT: u32 = 20;
pub const EASING_EXPO_INOUT: u32 = 21;
pub const EASING_ELASTIC_IN: u32 = 22;
pub const EASING_ELASTIC_OUT: u32 = 23;
pub const EASING_ELASTIC_INOUT: u32 = 24;
pub const EASING_BACK_IN: u32 = 25;
pub const EASING_BACK_OUT: u32 = 26;
pub const EASING_BACK_INOUT: u32 = 27;
pub const EASING_BOUNCE_IN: u32 = 28;
pub const EASING_BOUNCE_OUT: u32 = 29;
pub const EASING_BOUNCE_INOUT: u32 = 30;

static EASINGS: Lazy<HashMap<u32, fn(f64) -> f64>> = Lazy::new(|| {
    [
        (EASING_LINEAR, linear as fn(f64) -> f64),
        (EASING_QUAD_IN, ezing::quad_in::<f64> as fn(f64) -> f64),
        (EASING_QUAD_OUT, ezing::quad_out::<f64>),
        (EASING_QUAD_INOUT, ezing::quad_inout::<f64>),
        (EASING_CUBIC_IN, ezing::cubic_in::<f64>),
        (EASING_CUBIC_OUT, ezing::cubic_out::<f64>),
        (EASING_CUBIC_INOUT, ezing::cubic_inout::<f64>),
        (EASING_QUART_IN, ezing::quart_in::<f64>),
        (EASING_QUART_OUT, ezing::quart_out::<f64>),
        (EASING_QUART_INOUT, ezing::quart_inout::<f64>),
        (EASING_QUINT_IN, ezing::quint_in::<f64>),
        (EASING_QUINT_OUT, ezing::quint_out::<f64>),
        (EASING_QUINT_INOUT, ezing::quint_inout::<f64>),
        (EASING_SINE_IN, ezing::sine_in::<f64>),
        (EASING_SINE_OUT, ezing::sine_out::<f64>),
        (EASING_SINE_INOUT, ezing::sine_inout::<f64>),
        (EASING_CIRC_IN, ezing::circ_in::<f64>),
        (EASING_CIRC_OUT, ezing::circ_out::<f64>),
        (EASING_CIRC_INOUT, ezing::circ_inout::<f64>),
        (EASING_EXPO_IN, ezing::expo_in::<f64>),
        (EASING_EXPO_OUT, ezing::expo_out::<f64>),
        (EASING_EXPO_INOUT, ezing::expo_inout::<f64>),
        (EASING_ELASTIC_IN, ezing::elastic_in::<f64>),
        (EASING_ELASTIC_OUT, ezing::elastic_out::<f64>),
        (EASING_ELASTIC_INOUT, ezing::elastic_inout::<f64>),
        (EASING_BACK_IN, ezing::back_in::<f64>),
        (EASING_BACK_OUT, ezing::back_out::<f64>),
        (EASING_BACK_INOUT, ezing::back_inout::<f64>),
        (EASING_BOUNCE_IN, ezing::bounce_in::<f64>),
        (EASING_BOUNCE_OUT, ezing::bounce_out::<f64>),
        (EASING_BOUNCE_INOUT, ezing::bounce_inout::<f64>),
    ]
    .iter()
    .cloned()
    .collect()
});

static EASING_CHOICES: Lazy<Vec<u32>> = Lazy::new(|| EASINGS.keys().map(|&k| k).collect());

pub trait StdRngExt {
    fn gen_easing(&mut self) -> u32;
}

impl StdRngExt for StdRng {
    fn gen_easing(&mut self) -> u32 {
        EASING_CHOICES[self.gen_range(0, EASING_CHOICES.len())]
    }
}

pub fn serialize_easing<S>(value: &u32, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    let representation = match *value {
        EASING_LINEAR => "linear",
        EASING_QUAD_IN => "quad_in",
        EASING_QUAD_OUT => "quad_out",
        EASING_QUAD_INOUT => "quad_inout",
        EASING_CUBIC_IN => "cubic_in",
        EASING_CUBIC_OUT => "cubic_out",
        EASING_CUBIC_INOUT => "cubic_inout",
        EASING_QUART_IN => "quart_in",
        EASING_QUART_OUT => "quart_out",
        EASING_QUART_INOUT => "quart_inout",
        EASING_QUINT_IN => "quint_in",
        EASING_QUINT_OUT => "quint_out",
        EASING_QUINT_INOUT => "quint_inout",
        EASING_SINE_IN => "sine_in",
        EASING_SINE_OUT => "sine_out",
        EASING_SINE_INOUT => "sine_inout",
        EASING_CIRC_IN => "circ_in",
        EASING_CIRC_OUT => "circ_out",
        EASING_CIRC_INOUT => "circ_inout",
        EASING_EXPO_IN => "expo_in",
        EASING_EXPO_OUT => "expo_out",
        EASING_EXPO_INOUT => "expo_inout",
        EASING_ELASTIC_IN => "elastic_in",
        EASING_ELASTIC_OUT => "elastic_out",
        EASING_ELASTIC_INOUT => "elastic_inout",
        EASING_BACK_IN => "back_in",
        EASING_BACK_OUT => "back_out",
        EASING_BACK_INOUT => "back_inout",
        EASING_BOUNCE_IN => "bounce_in",
        EASING_BOUNCE_OUT => "bounce_out",
        EASING_BOUNCE_INOUT => "bounce_inout",
        _ => panic!("unknown easing value: {}", value),
    };
    serializer.serialize_str(representation)
}

pub fn deserialize_easing<'de, D>(deserializer: D) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: String = Deserialize::deserialize(deserializer)?;
    Ok(match representation.as_ref() {
        "linear" => EASING_LINEAR,
        "quad_in" => EASING_QUAD_IN,
        "quad_out" => EASING_QUAD_OUT,
        "quad_inout" => EASING_QUAD_INOUT,
        "cubic_in" => EASING_CUBIC_IN,
        "cubic_out" => EASING_CUBIC_OUT,
        "cubic_inout" => EASING_CUBIC_INOUT,
        "quart_in" => EASING_QUART_IN,
        "quart_out" => EASING_QUART_OUT,
        "quart_inout" => EASING_QUART_INOUT,
        "quint_in" => EASING_QUINT_IN,
        "quint_out" => EASING_QUINT_OUT,
        "quint_inout" => EASING_QUINT_INOUT,
        "sine_in" => EASING_SINE_IN,
        "sine_out" => EASING_SINE_OUT,
        "sine_inout" => EASING_SINE_INOUT,
        "circ_in" => EASING_CIRC_IN,
        "circ_out" => EASING_CIRC_OUT,
        "circ_inout" => EASING_CIRC_INOUT,
        "expo_in" => EASING_EXPO_IN,
        "expo_out" => EASING_EXPO_OUT,
        "expo_inout" => EASING_EXPO_INOUT,
        "elastic_in" => EASING_ELASTIC_IN,
        "elastic_out" => EASING_ELASTIC_OUT,
        "elastic_inout" => EASING_ELASTIC_INOUT,
        "back_in" => EASING_BACK_IN,
        "back_out" => EASING_BACK_OUT,
        "back_inout" => EASING_BACK_INOUT,
        "bounce_in" => EASING_BOUNCE_IN,
        "bounce_out" => EASING_BOUNCE_OUT,
        "bounce_inout" => EASING_BOUNCE_INOUT,
        _ => panic!("unknown easing representation: {}", representation),
    })
}

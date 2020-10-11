use juno_rs::indicators::{self, MA};
use once_cell::sync::Lazy;
use serde::Deserialize;
use std::{collections::HashMap, fs::File};

static DATA: Lazy<HashMap<String, IndicatorData>> = Lazy::new(|| {
    // Relative to juno_rs dir.
    let file =
        File::open("../tests/data/indicators.yaml").expect("unable to open indicators data file");
    serde_yaml::from_reader(file).expect("unable to deserialize indicator data")
});

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[derive(Deserialize)]
struct IndicatorData {
    inputs: Vec<Vec<String>>,
    outputs: Vec<Vec<String>>,
}

#[test]
fn test_adx() -> Result<()> {
    let mut indicator = indicators::Adx::new(14);
    assert(
        "adx",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?, inputs[1][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_alma() -> Result<()> {
    let mut indicator = indicators::Alma::with_sigma(9, 6);
    assert(
        "alma",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_dema() -> Result<()> {
    let mut indicator = indicators::Dema::new(5);
    assert(
        "dema",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_di() -> Result<()> {
    let mut indicator = indicators::DI::new(14);
    assert(
        "di",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?, inputs[1][i].parse()?, inputs[2][i].parse()?);
            Ok(vec![indicator.plus_value, indicator.minus_value])
        },
    )
}

#[test]
fn test_dm() -> Result<()> {
    let mut indicator = indicators::DM::new(14);
    assert(
        "dm",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?, inputs[1][i].parse()?);
            Ok(vec![indicator.plus_value, indicator.minus_value])
        },
    )
}

#[test]
fn test_dx() -> Result<()> {
    let mut indicator = indicators::DX::new(14);
    assert(
        "dx",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?, inputs[1][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_ema() -> Result<()> {
    let mut indicator = indicators::Ema::new(5);
    assert(
        "ema",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_kama() -> Result<()> {
    let mut indicator = indicators::Kama::new(4);
    assert(
        "kama",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_macd() -> Result<()> {
    let mut indicator = indicators::Macd::new(12, 26, 9);
    assert(
        "macd",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?);
            Ok(vec![indicator.value, indicator.signal, indicator.histogram])
        },
    )
}

#[test]
fn test_rsi() -> Result<()> {
    let mut indicator = indicators::Rsi::new(5);
    assert(
        "rsi",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_sma() -> Result<()> {
    let mut indicator = indicators::Sma::new(5);
    assert(
        "sma",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?);
            Ok(vec![indicator.value])
        },
    )
}

#[test]
fn test_stoch() -> Result<()> {
    let mut indicator = indicators::Stoch::new(5, 3, 3);
    assert(
        "stoch",
        |inputs, i| {
            indicator.update(inputs[0][i].parse()?, inputs[1][i].parse()?, inputs[2][i].parse()?);
            Ok(vec![indicator.k, indicator.d])
        },
    )
}

fn assert<T>(name: &str, mut update: T) -> Result<()>
where
    T: FnMut(&Vec<Vec<String>>, usize) -> Result<Vec<f64>>,
 {
    let data = &DATA[name];
    let input_len = data.inputs[0].len();
    let output_len = data.outputs[0].len();
    let offset = input_len - output_len;
    for i in 0..input_len {
        let values = update(&data.inputs, i)?;
        if i >= offset {
            for j in 0..data.outputs.len() {
                let expected: f64 = data.outputs[j][i - offset].parse()?;
                let value = values[j];
                let diff = f64::abs(value - expected);
                assert!(
                    diff < 0.001,
                    format!("expected {} but got {}; diff is {}", expected, value, diff)
                );
            }
        }
    }
    Ok(())
}



// def test_adx(data) -> None:
//     _assert(indicators.Adx(14), data['adx'], 4)

use juno_rs::indicators;
use once_cell::sync::Lazy;
use serde::Deserialize;
use std::{collections::HashMap, fs::File};

static DATA: Lazy<HashMap<String, IndicatorData>> = Lazy::new(|| {
    // Relative to juno_rs dir.
    let file =
        File::open("../tests/data/indicators.yaml").expect("unable to open indicators data file");
    serde_yaml::from_reader(file).expect("unable to deserialize indicator data")
});

type Result = std::result::Result<(), Box<dyn std::error::Error>>;

#[derive(Deserialize)]
struct IndicatorData {
    inputs: Vec<Vec<String>>,
    outputs: Vec<Vec<String>>,
}

#[test]
fn test_adx() -> Result {
    let data = &DATA["adx"];

    let mut indicator = indicators::Adx::new(14);

    let input_len = data.inputs[0].len();
    let output_len = data.outputs[0].len();
    let offset = input_len - output_len;
    for i in 0..input_len {
        indicator.update(data.inputs[0][i].parse()?, data.inputs[1][i].parse()?);
        if i >= offset {
            let value = indicator.value;
            let expected: f64 = data.outputs[0][i - offset].parse()?;
            let diff = f64::abs(value - expected);
            assert!(
                diff < 0.001,
                format!("expected {} but got {}; diff is {}", expected, value, diff)
            );
        }
    }
    Ok(())

    // assert_eq!(adder::add(3, 2), 5);
}

// fn assert(indicator: ) {

// }

// def test_adx(data) -> None:
//     _assert(indicators.Adx(14), data['adx'], 4)

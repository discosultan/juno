use crate::{
    indicators::adler32,
    time::{IntervalIntExt, IntervalStrExt, TimestampIntExt, TimestampStrExt},
};
use serde::{Deserialize, Deserializer, Serializer};

fn serialize_ma<S>(value: &u32, serializer: S) -> Result<S::Ok, S::Error> where S: Serializer {
    let representation = match *value {
        adler32::ALMA => "alma",
        adler32::DEMA => "dema",
        adler32::EMA  => "ema",
        adler32::EMA2 => "ema2",
        adler32::KAMA => "kama",
        adler32::SMA  => "sma",
        adler32::SMMA => "smma",
        _ => panic!("unknown ma value: {}", value),
    };
    serializer.serialize_str(representation)
}

fn deserialize_ma<'de, D>(deserializer: D) -> Result<u32, D::Error> where D: Deserializer<'de> {
    let representation: &str = Deserialize::deserialize(deserializer)?;
    Ok(match representation {
        "alma" => adler32::ALMA,
        "dema" => adler32::DEMA,
        "ema"  => adler32::EMA,
        "ema2" => adler32::EMA2,
        "kama" => adler32::KAMA,
        "sma"  => adler32::SMA,
        "smma" => adler32::SMMA,
        _ => panic!("unknown ma representation: {}", representation),
    })
}

fn serialize_interval<S>(value: &u64, serializer: S) -> Result<S::Ok, S::Error> where S: Serializer {
    serializer.serialize_str(value.to_interval_repr())
}

fn deserialize_interval<'de, D>(deserializer: D) -> Result<u64, D::Error> where D: Deserializer<'de> {
    let representation: &str = Deserialize::deserialize(deserializer)?;
    Ok(representation.to_interval())
}

fn serialize_timestamp<S>(value: &u64, serializer: S) -> Result<S::Ok, S::Error> where S: Serializer {
    serializer.serialize_str(&value.to_timestamp_repr())
}

fn deserialize_timestamp<'de, D>(deserializer: D) -> Result<u64, D::Error> where D: Deserializer<'de> {
    let representation: &str = Deserialize::deserialize(deserializer)?;
    Ok(representation.to_timestamp())
}

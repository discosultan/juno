use crate::{
    indicators::adler32,
    strategies::MidTrend,
    time::{IntervalIntExt, IntervalStrExt, TimestampIntExt, TimestampStrExt},
    trading,
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

fn serialize_missed_candle_policy<S>(
    value: &u32, serializer: S
) -> Result<S::Ok, S::Error> where S: Serializer {
    let representation = match *value {
        trading::MISSED_CANDLE_POLICY_IGNORE  => "ignore",
        trading::MISSED_CANDLE_POLICY_LAST    => "last",
        trading::MISSED_CANDLE_POLICY_RESTART => "restart",
        _ => panic!("unknown missed candle policy value: {}", value),
    };
    serializer.serialize_str(representation)
}

fn deserialize_missed_candle_policy<'de, D>(
    deserializer: D
) -> Result<u32, D::Error> where D: Deserializer<'de> {
    let representation: &str = Deserialize::deserialize(deserializer)?;
    Ok(match representation {
        "ignore"  => trading::MISSED_CANDLE_POLICY_IGNORE,
        "last"    => trading::MISSED_CANDLE_POLICY_LAST,
        "restart" => trading::MISSED_CANDLE_POLICY_RESTART,
        _ => panic!("unknown missed candle policy representation: {}", representation),
    })
}

fn serialize_mid_trend_policy<S>(
    value: &u32, serializer: S
) -> Result<S::Ok, S::Error> where S: Serializer {
    let representation = match *value {
        MidTrend::POLICY_CURRENT  => "current",
        MidTrend::POLICY_IGNORE   => "ignore",
        MidTrend::POLICY_PREVIOUS => "previous",
        _ => panic!("unknown mid trend policy value: {}", value),
    };
    serializer.serialize_str(representation)
}

fn deserialize_mid_trend_policy<'de, D>(
    deserializer: D
) -> Result<u32, D::Error> where D: Deserializer<'de> {
    let representation: &str = Deserialize::deserialize(deserializer)?;
    Ok(match representation {
        "current"  => MidTrend::POLICY_CURRENT,
        "ignore"   => MidTrend::POLICY_IGNORE,
        "previous" => MidTrend::POLICY_PREVIOUS,
        _ => panic!("unknown mid trend policy representation: {}", representation),
    })
}

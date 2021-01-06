use chrono::prelude::*;
use serde::{Deserialize, Deserializer, Serializer};
use std::time::{SystemTime, UNIX_EPOCH};

pub const SEC_MS: u64 = 1000;
pub const MIN_MS: u64 = 60_000;
pub const HOUR_MS: u64 = 3_600_000;
pub const DAY_MS: u64 = 86_400_000;
pub const WEEK_MS: u64 = 604_800_000;
pub const MONTH_MS: u64 = 2_629_746_000;
pub const YEAR_MS: u64 = 31_556_952_000;

// Interval.

// Is assumed to be ordered by values descending.
const INTERVAL_FACTORS: [(&str, u64); 8] = [
    ("y", YEAR_MS),
    ("M", MONTH_MS),
    ("w", WEEK_MS),
    ("d", DAY_MS),
    ("h", HOUR_MS),
    ("m", MIN_MS),
    ("s", SEC_MS),
    ("", 1),
];

fn str_to_interval(representation: &str) -> u64 {
    match representation {
        "1m" => 60_000,
        "3m" => 180_000,
        "5m" => 300_000,
        "15m" => 900_000,
        "30m" => 1_800_000,
        "1h" => 3_600_000,
        "2h" => 7_200_000,
        "4h" => 14_400_000,
        "6h" => 21_600_000,
        "8h" => 28_800_000,
        "12h" => 43_200_000,
        "1d" => 86_400_000,
        "3d" => 259_200_000,
        "1w" => 604_800_000,
        "1M" => 2_629_746_000,
        _ => panic!("unknown interval representation: {}", representation),
    }
}

fn interval_to_string(value: u64) -> String {
    let mut result = String::new();
    let mut remainder = value;
    for (letter, factor) in INTERVAL_FACTORS.iter() {
        let quotient = remainder / factor;
        remainder = remainder % factor;
        if quotient > 0 {
            result.push_str(&format!("{}{}", quotient, letter));
        }
        if remainder == 0 {
            break;
        }
    }
    if result == "" {
        result.push('0');
    }
    result
}

pub trait IntervalStrExt {
    fn to_interval(&self) -> u64;
}

impl IntervalStrExt for str {
    fn to_interval(&self) -> u64 {
        str_to_interval(self)
    }
}

pub trait IntervalIntExt {
    fn to_interval_repr(self) -> String;
}

impl IntervalIntExt for u64 {
    fn to_interval_repr(self) -> String {
        interval_to_string(self)
    }
}

pub fn serialize_interval<S>(value: &u64, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    serializer.serialize_str(&interval_to_string(*value))
}

pub fn deserialize_interval<'de, D>(deserializer: D) -> Result<u64, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(str_to_interval(Deserialize::deserialize(deserializer)?))
}

pub fn serialize_interval_option<S>(value: &Option<u64>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    match value {
        Some(value) => serializer.serialize_str(&interval_to_string(*value)),
        None => serializer.serialize_none(),
    }
}

pub fn deserialize_interval_option<'de, D>(deserializer: D) -> Result<Option<u64>, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: Option<&str> = Deserialize::deserialize(deserializer)?;
    Ok(representation.map(|repr| str_to_interval(repr)))
}

// Timestamp.

pub fn timestamp() -> u64 {
    let start = SystemTime::now();
    let since_the_epoch = start
        .duration_since(UNIX_EPOCH)
        .expect("duration since epoch");
    since_the_epoch.as_secs() * 1000 + u64::from(since_the_epoch.subsec_nanos()) / 1_000_000
}

fn str_to_timestamp(representation: &str) -> u64 {
    Err(())
        .or_else(|_| {
            representation
                .parse::<DateTime<Utc>>()
                .map(|x| x.timestamp() as u64 * 1000 + u64::from(x.timestamp_subsec_millis()))
        })
        .or_else(|_| {
            representation
                .parse::<NaiveDateTime>()
                .map(|x| x.timestamp() as u64 * 1000 + u64::from(x.timestamp_subsec_millis()))
        })
        .or_else(|_| {
            representation
                .parse::<NaiveDate>()
                .map(|x| x.and_hms(0, 0, 0).timestamp() as u64 * 1000)
        })
        .expect("parsed timestamp")
}

fn timestamp_to_string(value: u64) -> String {
    let datetime = Utc.timestamp_millis(value as i64);
    // datetime.to_rfc3339()
    datetime.format("%Y-%m-%dT%H:%M:%S").to_string()
}

pub trait TimestampStrExt {
    fn to_timestamp(&self) -> u64;
}

impl TimestampStrExt for str {
    fn to_timestamp(&self) -> u64 {
        str_to_timestamp(self)
    }
}

pub trait TimestampIntExt {
    fn to_timestamp_repr(&self) -> String;
}

impl TimestampIntExt for u64 {
    fn to_timestamp_repr(&self) -> String {
        timestamp_to_string(*self)
    }
}

pub fn serialize_timestamp<S>(value: &u64, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    serializer.serialize_str(&timestamp_to_string(*value))
}

pub fn deserialize_timestamp<'de, D>(deserializer: D) -> Result<u64, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(str_to_timestamp(Deserialize::deserialize(deserializer)?))
}

pub fn serialize_timestamp_option<S>(value: &Option<u64>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    match value {
        Some(value) => serializer.serialize_str(&timestamp_to_string(*value)),
        None => serializer.serialize_none(),
    }
}

pub fn deserialize_timestamp_option<'de, D>(deserializer: D) -> Result<Option<u64>, D::Error>
where
    D: Deserializer<'de>,
{
    let representation: Option<&str> = Deserialize::deserialize(deserializer)?;
    Ok(representation.map(|repr| str_to_timestamp(repr)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_interval_to_repr() {
        assert_eq!((DAY_MS * 2).to_interval_repr(), "2d");
        assert_eq!(123.to_interval_repr(), "123");
        assert_eq!(1234.to_interval_repr(), "1s234");
        assert_eq!(0.to_interval_repr(), "0");
    }

    #[test]
    fn test_interval_from_repr() {
        assert_eq!("1d".to_interval(), DAY_MS);
        // assert_eq!("2d".to_interval(), DAY_MS * 2);
    }

    #[test]
    fn test_timestamp_to_repr() {
        assert_eq!(
            1546300800000.to_timestamp_repr(),
            // "2019-01-01T00:00:00+00:00"
            "2019-01-01T00:00:00"
        );
    }

    #[test]
    fn test_timestamp_from_repr() {
        assert_eq!("2019-01-01".to_timestamp(), 1546300800000);
    }
}

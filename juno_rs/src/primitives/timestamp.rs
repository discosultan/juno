use crate::math::floor_multiple;

use super::Interval;
use chrono::prelude::*;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::{fmt, ops, time::{SystemTime, UNIX_EPOCH}};

fn timestamp() -> u64 {
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

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct Timestamp(pub u64);

impl Timestamp {
    pub fn now() -> Self {
        Self(timestamp())
    }

    pub fn floor_multiple(self, interval: Interval) -> Self {
        Timestamp(floor_multiple(self.0, interval.0))
    }
}

impl ops::Add<Interval> for Timestamp {
    type Output = Self;

    fn add(self, other: Interval) -> Self::Output {
        Self(self.0 + other.0)
    }
}

impl ops::AddAssign<Interval> for Timestamp {
    fn add_assign(&mut self, other: Interval) {
        self.0 += other.0;
    }
}

impl ops::Sub for Timestamp {
    type Output = Interval;

    fn sub(self, other: Self) -> Self::Output {
        Interval(self.0 - other.0)
    }
}

// impl ops::Div<Interval> for Timestamp {
//     type Output = usize;

//     fn div(self, rhs: Interval) -> Self::Output {
//         (self.0 / rhs.0) as usize
//     }
// }

impl ops::Rem<Interval> for Timestamp {
    type Output = Interval;

    fn rem(self, modulus: Interval) -> Self::Output {
        Interval(self.0 % modulus.0)
    }
}

impl fmt::Display for Timestamp {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", &timestamp_to_string(self.0))
    }
}

impl From<u64> for Timestamp {
    fn from(item: u64) -> Self {
        Timestamp(item)
    }
}

impl From<&str> for Timestamp {
    fn from(item: &str) -> Self {
        Timestamp(str_to_timestamp(item))
    }
}

impl From<Timestamp> for String {
    fn from(item: Timestamp) -> Self {
        timestamp_to_string(item.0)
    }
}

impl From<Timestamp> for u64 {
    fn from(item: Timestamp) -> Self {
        item.0
    }
}

impl Serialize for Timestamp {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&timestamp_to_string(self.0))
    }
}

impl<'de> Deserialize<'de> for Timestamp {
    fn deserialize<D>(deserializer: D) -> Result<Timestamp, D::Error>
    where
        D: Deserializer<'de>,
    {
        Ok(Timestamp(str_to_timestamp(Deserialize::deserialize(deserializer)?)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_timestamp_to_repr() {
        assert_eq!(
            timestamp_to_string(1546300800000),
            // "2019-01-01T00:00:00+00:00"
            "2019-01-01T00:00:00"
        );
    }

    #[test]
    fn test_timestamp_from_repr() {
        assert_eq!(str_to_timestamp("2019-01-01"), 1546300800000);
    }
}

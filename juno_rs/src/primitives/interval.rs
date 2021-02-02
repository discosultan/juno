use once_cell::sync::Lazy;
use regex::Regex;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::{collections::HashMap, convert::From, fmt, ops};

use crate::math::ceil_multiple;

const SEC_MS: u64 = 1000;
const MIN_MS: u64 = 60_000;
const HOUR_MS: u64 = 3_600_000;
const DAY_MS: u64 = 86_400_000;
const WEEK_MS: u64 = 604_800_000;
const MONTH_MS: u64 = 2_629_746_000;
const YEAR_MS: u64 = 31_556_952_000;

// Is assumed to be ordered by values descending.
const INTERVAL_FACTORS: [(&str, u64); 8] = [
    ("y", YEAR_MS),
    ("M", MONTH_MS),
    ("w", WEEK_MS),
    ("d", DAY_MS),
    ("h", HOUR_MS),
    ("m", MIN_MS),
    ("s", SEC_MS),
    ("ms", 1),
];

static INTERVAL_FACTOR_MAP: Lazy<HashMap<&'static str, u64>> =
    Lazy::new(|| INTERVAL_FACTORS.iter().cloned().collect());

static INTERVAL_GROUP_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(\d+[a-zA-Z]+)").unwrap());

fn str_to_interval(representation: &str) -> u64 {
    INTERVAL_GROUP_RE
        .find_iter(representation)
        .fold(0, |acc, group| acc + calc_interval_group(group.as_str()))
}

fn calc_interval_group(group: &str) -> u64 {
    for (i, c) in group.chars().enumerate() {
        if c.is_alphabetic() {
            return group[0..i].parse::<u64>().unwrap() * INTERVAL_FACTOR_MAP[&group[i..]];
        }
    }
    panic!("Invalid interval group: {}", group);
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
        result.push_str("0ms");
    }
    result
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq, PartialOrd)]
pub struct Interval(pub u64);

impl Interval {
    pub const SEC_MS: Interval = Interval(SEC_MS);
    pub const MIN_MS: Interval = Interval(MIN_MS);
    pub const HOUR_MS: Interval = Interval(HOUR_MS);
    pub const DAY_MS: Interval = Interval(DAY_MS);
    pub const WEEK_MS: Interval = Interval(WEEK_MS);
    pub const MONTH_MS: Interval = Interval(MONTH_MS);
    pub const YEAR_MS: Interval = Interval(YEAR_MS);

    pub fn ceil_multiple(self, other: Interval) -> Self {
        Self(ceil_multiple(self.0, other.0))
    }
}

impl ops::Add for Interval {
    type Output = Self;

    fn add(self, other: Self) -> Self {
        Self(self.0 + other.0)
    }
}

impl ops::AddAssign for Interval {
    fn add_assign(&mut self, other: Self) {
        self.0 += other.0;
    }
}

impl ops::Sub for Interval {
    type Output = Self;

    fn sub(self, other: Self) -> Self::Output {
        Self(self.0 - other.0)
    }
}

impl ops::Mul<Interval> for usize {
    type Output = Interval;

    fn mul(self, rhs: Interval) -> Self::Output {
        Interval(self as u64 * rhs.0)
    }
}

impl ops::Mul<usize> for Interval {
    type Output = Interval;

    fn mul(self, rhs: usize) -> Self::Output {
        Interval(self.0 * rhs as u64)
    }
}

impl ops::Div for Interval {
    type Output = usize;

    fn div(self, rhs: Interval) -> Self::Output {
        (self.0 / rhs.0) as usize
    }
}

impl ops::Div<usize> for Interval {
    type Output = Interval;

    fn div(self, rhs: usize) -> Self::Output {
        Self(self.0 / rhs as u64)
    }
}

impl fmt::Display for Interval {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", &interval_to_string(self.0))
    }
}

impl From<u64> for Interval {
    fn from(item: u64) -> Self {
        Interval(item)
    }
}

impl From<&str> for Interval {
    fn from(item: &str) -> Self {
        Interval(str_to_interval(item))
    }
}

impl From<Interval> for String {
    fn from(item: Interval) -> Self {
        interval_to_string(item.0)
    }
}

impl From<Interval> for u64 {
    fn from(item: Interval) -> Self {
        item.0
    }
}

impl Serialize for Interval {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&interval_to_string(self.0))
    }
}

impl<'de> Deserialize<'de> for Interval {
    fn deserialize<D>(deserializer: D) -> Result<Interval, D::Error>
    where
        D: Deserializer<'de>,
    {
        Ok(Interval(str_to_interval(Deserialize::deserialize(deserializer)?)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_interval_to_repr() {
        assert_eq!(interval_to_string(DAY_MS * 2), "2d");
        assert_eq!(interval_to_string(123), "123ms");
        assert_eq!(interval_to_string(1234), "1s234ms");
        assert_eq!(interval_to_string(0), "0ms");
    }

    #[test]
    fn test_interval_from_repr() {
        assert_eq!(str_to_interval("1d"), DAY_MS);
        assert_eq!(str_to_interval("2d"), DAY_MS * 2);
        assert_eq!(str_to_interval("1s1ms"), SEC_MS + 1);
        assert_eq!(str_to_interval("1m1s"), MIN_MS + SEC_MS);
    }
}

// garbage

// pub trait IntervalStrExt {
//     fn to_interval(&self) -> u64;
// }

// impl IntervalStrExt for str {
//     fn to_interval(&self) -> u64 {
//         str_to_interval(self)
//     }
// }

// pub trait IntervalIntExt {
//     fn to_interval_repr(self) -> String;
// }

// impl IntervalIntExt for u64 {
//     fn to_interval_repr(self) -> String {
//         interval_to_string(self)
//     }
// }

// pub fn serialize_interval<S>(value: &u64, serializer: S) -> Result<S::Ok, S::Error>
// where
//     S: Serializer,
// {
//     serializer.serialize_str(&interval_to_string(*value))
// }

// pub fn deserialize_interval<'de, D>(deserializer: D) -> Result<u64, D::Error>
// where
//     D: Deserializer<'de>,
// {
//     let representation: String = Deserialize::deserialize(deserializer)?;
//     Ok(str_to_interval(&representation))
// }

// pub fn serialize_interval_option<S>(value: &Option<u64>, serializer: S) -> Result<S::Ok, S::Error>
// where
//     S: Serializer,
// {
//     match value {
//         Some(value) => serializer.serialize_str(&interval_to_string(*value)),
//         None => serializer.serialize_none(),
//     }
// }

// pub fn deserialize_interval_option<'de, D>(deserializer: D) -> Result<Option<u64>, D::Error>
// where
//     D: Deserializer<'de>,
// {
//     let representation: Option<String> = Deserialize::deserialize(deserializer)?;
//     Ok(representation.map(|repr| str_to_interval(&repr)))
// }

// pub fn serialize_intervals<S>(values: &[u64], serializer: S) -> Result<S::Ok, S::Error>
// where
//     S: Serializer,
// {
//     let mut seq = serializer.serialize_seq(Some(values.len()))?;
//     for interval in values {
//         seq.serialize_element(&interval_to_string(*interval))?;
//     }
//     seq.end()
// }

// pub fn deserialize_intervals<'de, D>(deserializer: D) -> Result<Vec<u64>, D::Error>
// where
//     D: Deserializer<'de>,
// {
//     let representations: Vec<String> = Deserialize::deserialize(deserializer)?;
//     Ok(representations
//         .iter()
//         .map(|repr| str_to_interval(repr))
//         .collect())
// }

// pub fn serialize_intervals_option<S>(
//     value: &Option<Vec<u64>>,
//     serializer: S,
// ) -> Result<S::Ok, S::Error>
// where
//     S: Serializer,
// {
//     match value {
//         Some(value) => {
//             let mut seq = serializer.serialize_seq(Some(value.len()))?;
//             for interval in value {
//                 seq.serialize_element(&interval_to_string(*interval))?;
//             }
//             seq.end()
//         }
//         None => serializer.serialize_none(),
//     }
// }

// pub fn deserialize_intervals_option<'de, D>(deserializer: D) -> Result<Option<Vec<u64>>, D::Error>
// where
//     D: Deserializer<'de>,
// {
//     let representations: Option<Vec<String>> = Deserialize::deserialize(deserializer)?;
//     Ok(representations.map(|reprs| reprs.iter().map(|repr| str_to_interval(repr)).collect()))
// }
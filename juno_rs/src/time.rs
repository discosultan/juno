use chrono::prelude::*;
use std::time::{SystemTime, UNIX_EPOCH};

pub const SEC_MS: u64 = 1000;
pub const MIN_MS: u64 = 60_000;
pub const HOUR_MS: u64 = 3_600_000;
pub const DAY_MS: u64 = 86_400_000;
pub const WEEK_MS: u64 = 604_800_000;
pub const MONTH_MS: u64 = 2_629_746_000;
pub const YEAR_MS: u64 = 31_556_952_000;

// Interval.

pub trait IntervalStrExt {
    fn to_interval(&self) -> u64;
}

impl IntervalStrExt for str {
    fn to_interval(&self) -> u64 {
        match self {
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
            _ => panic!("unknown interval string"),
        }
    }
}

pub trait IntervalIntExt {
    fn to_interval_repr(self) -> &'static str;
}

impl IntervalIntExt for u64 {
    fn to_interval_repr(self) -> &'static str {
        match self {
            60_000 => "1m",
            180_000 => "3m",
            300_000 => "5m",
            900_000 => "15m",
            1_800_000 => "30m",
            3_600_000 => "1h",
            7_200_000 => "2h",
            14_400_000 => "4h",
            21_600_000 => "6h",
            28_800_000 => "8h",
            43_200_000 => "12h",
            86_400_000 => "1d",
            259_200_000 => "3d",
            604_800_000 => "1w",
            2_629_746_000 => "1M",
            _ => panic!("unknown interval"),
        }
    }
}

// Timestamp.

pub fn timestamp() -> u64 {
    let start = SystemTime::now();
    let since_the_epoch = start
        .duration_since(UNIX_EPOCH)
        .expect("duration since epoch");
    since_the_epoch.as_secs() * 1000 + u64::from(since_the_epoch.subsec_nanos()) / 1_000_000
}

pub trait TimestampStrExt {
    fn to_timestamp(&self) -> u64;
}

impl TimestampStrExt for str {
    fn to_timestamp(&self) -> u64 {
        Err(())
            .or_else(|_| {
                self.parse::<DateTime<Utc>>()
                    .map(|x| x.timestamp() as u64 * 1000 + u64::from(x.timestamp_subsec_millis()))
            })
            .or_else(|_| {
                self.parse::<NaiveDateTime>()
                    .map(|x| x.timestamp() as u64 * 1000 + u64::from(x.timestamp_subsec_millis()))
            })
            .or_else(|_| {
                self.parse::<NaiveDate>()
                    .map(|x| x.and_hms(0, 0, 0).timestamp() as u64 * 1000)
            })
            .expect("parsed timestamp")
    }
}

pub trait TimestampIntExt {
    fn to_timestamp_repr(&self) -> String;
}

impl TimestampIntExt for u64 {
    fn to_timestamp_repr(&self) -> String {
        let datetime = Utc.timestamp_millis(*self as i64);
        datetime.to_rfc3339()
    }
}

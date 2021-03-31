pub fn ceil_multiple(value: u64, multiple: u64) -> u64 {
    f64::ceil(value as f64 / multiple as f64) as u64 * multiple
}

pub fn ceil_multiple_offset(value: u64, multiple: u64, offset: u64) -> u64 {
    ceil_multiple(value - offset, multiple) + offset
}

pub fn floor_multiple(value: u64, multiple: u64) -> u64 {
    value - (value % multiple)
}

pub fn floor_multiple_offset(value: u64, multiple: u64, offset: u64) -> u64 {
    floor_multiple(value - offset, multiple) + offset
}

pub fn mean(data: &[f64]) -> f64 {
    let count = data.len();
    if count == 0 {
        f64::NAN
    } else {
        let sum = data.iter().sum::<f64>();
        sum / count as f64
    }
}

pub fn std_deviation(data: &[f64]) -> f64 {
    let count = data.len();
    if count == 0 {
        f64::NAN
    } else {
        let sum = data.iter().sum::<f64>();
        let mean = sum / count as f64;
        let variance = data
            .iter()
            .map(|value| {
                let diff = mean - value;

                diff * diff
            })
            .sum::<f64>()
            / count as f64;
        variance.sqrt()
    }
}

pub fn round_down(value: f64, precision: u32) -> f64 {
    let factor = 10_u32.pow(precision) as f64;
    (value * factor).floor() / factor
}

pub fn round_half_up(value: f64, precision: u32) -> f64 {
    let factor = 10_u32.pow(precision) as f64;
    (value * factor).round() / factor
}

pub fn adler32(value: &str) -> u32 {
    const MODADLER: u32 = 65521;
    let mut a: u32 = 1;
    let mut b: u32 = 0;

    for c in value.chars() {
        a = a.wrapping_add(c as u32) % MODADLER;
        b = b.wrapping_add(a) % MODADLER;
    }

    b.wrapping_shl(16) | a
}

pub fn annualized(duration: u64, value: f64) -> f64 {
    const YEAR_MS: f64 = 31_556_952_000.0;

    let n = duration as f64 / YEAR_MS;
    if n == 0.0 {
        0.0
    } else {
        let res = (1.0 + value).powf(1.0 / n) - 1.0;
        if res == f64::NAN {
            0.0
        } else {
            res
        }
    }
}

pub fn lerp(a: f64, b: f64, t: f64) -> f64 {
    t * a + (1.0 - t) * b
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ceil_multiple() {
        assert_eq!(ceil_multiple(1, 5), 5);
        assert_eq!(ceil_multiple(5, 5), 5);
        assert_eq!(ceil_multiple(6, 5), 10);
    }

    #[test]
    fn test_ceil_multiple_offset() {
        assert_eq!(ceil_multiple_offset(4, 2, 1), 5);
    }

    #[test]
    fn test_floor_multiple() {
        assert_eq!(floor_multiple(1, 5), 0);
        assert_eq!(floor_multiple(5, 5), 5);
        assert_eq!(floor_multiple(6, 5), 5);
    }

    #[test]
    fn test_floor_multiple_offset() {
        assert_eq!(floor_multiple_offset(4, 2, 1), 3);
    }

    #[test]
    fn test_mean() {
        assert_eq!(mean(&[1.0, 2.0, 3.0]), 2.0)
    }

    #[test]
    fn test_round_down() {
        assert_eq!(round_down(0.004943799, 8), 0.00494379);
    }

    #[test]
    fn test_round_half_up() {
        assert_eq!(round_half_up(0.123, 2), 0.12);
        assert_eq!(round_half_up(0.120, 2), 0.12);
        assert_eq!(round_half_up(0.115, 2), 0.12);
    }

    #[test]
    fn test_adler32() {
        assert_eq!(adler32("sma"), 43_450_690);
        assert_eq!(adler32("ema"), 40_698_164);
    }

    #[test]
    fn test_lerp() {
        assert_eq!(lerp(-1.0, 3.0, 0.5), 1.0);
    }
}

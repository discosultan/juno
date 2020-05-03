pub fn ceil_multiple(value: u64, multiple: u64) -> u64 {
    f64::ceil(value as f64 / multiple as f64) as u64 * multiple
}

pub fn floor_multiple(value: u64, multiple: u64) -> u64 {
    value - (value % multiple)
}

pub fn mean(list: &[f64]) -> f64 {
    let sum: f64 = list.iter().sum();
    sum / (list.len() as f64)
}

pub fn round_down(value: f64, precision: u32) -> f64 {
    let factor = 10_u32.pow(precision) as f64;
    (value * factor).floor() / factor
}

pub fn round_half_up(value: f64, precision: u32) -> f64 {
    let factor = 10_u32.pow(precision) as f64;
    (value * factor).round() / factor
}

pub fn minmax<'a>(values: impl Iterator<Item = &'a f64>) -> (f64, f64) {
    let mut min = f64::MAX;
    let mut max = f64::MIN;
    for value in values {
        min = f64::min(min, *value);
        max = f64::max(max, *value);
    }
    (min, max)
}

#[cfg(test)]
mod tests {
    use super::{ceil_multiple, floor_multiple, mean, minmax, round_down, round_half_up};

    #[test]
    fn test_ceil_multiple() {
        assert_eq!(ceil_multiple(1, 5), 5);
        assert_eq!(ceil_multiple(5, 5), 5);
        assert_eq!(ceil_multiple(6, 5), 10);
    }

    #[test]
    fn test_floor_multiple() {
        assert_eq!(floor_multiple(1, 5), 0);
        assert_eq!(floor_multiple(5, 5), 5);
        assert_eq!(floor_multiple(6, 5), 5);
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
    fn test_minmax() {
        let vals = [3.0, 1.0, 2.0];
        assert_eq!(minmax(vals.iter()), (1.0, 3.0));
    }
}

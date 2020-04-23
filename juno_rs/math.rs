pub fn ceil_multiple(value: u64, multiple: u64) -> u64 {
    (value / multiple) * multiple
}

pub fn floor_multiple(value: u64, multiple: u64) -> u64 {
    value - (value % multiple)
}

pub fn mean(list: &[f64]) -> f64 {
    let sum: f64 = list.iter().sum();
    sum / (list.len() as f64)
}

pub fn round_half_up(value: f64, precision: u32) -> f64 {
    let factor = 10_u32.pow(precision) as f64;
    (value * factor).round() / factor
}

#[cfg(test)]
mod tests {
    use super::{ceil_multiple, floor_multiple, mean, round_half_up};

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
    fn test_round_half_up() {
        assert_eq!(round_half_up(0.123, 2), 0.12);
        assert_eq!(round_half_up(0.120, 2), 0.12);
        assert_eq!(round_half_up(0.115, 2), 0.12);
    }
}

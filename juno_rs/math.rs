use std::f64;

pub fn floor_multiple(value: u64, multiple: u64) -> u64 {
    value - (value % multiple)
}

pub fn round_half_up(value: f64, precision: u32) -> f64 {
    let factor = 10_u32.pow(precision) as f64;
    (value * factor).round() / factor
}

#[cfg(test)]
mod tests {
    use super::{floor_multiple, round_half_up};

    #[test]
    fn test_floor_multiple() {
        assert_eq!(floor_multiple(1, 5), 0);
        assert_eq!(floor_multiple(5, 5), 5);
        assert_eq!(floor_multiple(6, 5), 5);
    }

    #[test]
    fn test_round_half_up() {
        assert_eq!(round_half_up(0.123, 2), 0.12);
    }
}

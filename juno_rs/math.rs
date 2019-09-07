use std::f64;

pub fn round_half_up(value: f64, precision: u32) -> f64 {
    let factor = 10_u32.pow(precision) as f64;
    (value * factor).round() / factor
}

#[cfg(test)]
mod tests {
    use super::round_half_up;

    #[test]
    fn test_round_half_up() {
        assert_eq!(round_half_up(1.234, 2), 1.23);
    }
}

mod buffered_candle;
mod changed;
mod mid_trend;
mod persistence;

pub use buffered_candle::*;
pub use changed::*;
pub use mid_trend::*;
pub use persistence::*;

use crate::Advice;

pub fn combine(advice1: Advice, advice2: Advice) -> Advice {
    if advice1 == Advice::None || advice2 == Advice::None {
        Advice::None
    } else if advice1 == advice2 {
        advice1
    } else {
        Advice::Liquidate
    }
}

// TODO: Turn into iterator to reduce allocs.

pub fn merge_adjacent_spans(spans: &[(u64, u64)]) -> Vec<(u64, u64)> {
    let mut result = Vec::new();

    let mut merged_start = None;
    let mut merged_end = None;
    for &(start, end) in spans {
        if merged_start.is_none() {
            merged_start = Some(start);
            merged_end = Some(end);
        } else if merged_end == Some(start) {
            merged_end = Some(end);
        } else {
            result.push((merged_start.unwrap(), merged_end.unwrap()));
            merged_start = Some(start);
            merged_end = Some(end);
        }
    }

    if let Some(merged_start) = merged_start {
        result.push((merged_start, merged_end.unwrap()));
    }

    result
}

pub fn generate_missing_spans(
    start: u64,
    end: u64,
    existing_spans: &[(u64, u64)],
) -> Vec<(u64, u64)> {
    let mut result = Vec::new();

    // Initially assume entire span missing.
    let mut missing_start = start;
    let missing_end = end;

    // Spans are ordered by start_date. Spans do not overlap with each other.
    for &(existing_start, existing_end) in existing_spans {
        if existing_start > missing_start {
            result.push((missing_start, existing_start));
        }
        missing_start = existing_end;
    }

    if missing_start < missing_end {
        result.push((missing_start, missing_end));
    }

    result
}

pub fn page(start: u64, end: u64, interval: u64, limit: u64) -> impl Iterator<Item=(u64, u64)> {
    let total_size = (end - start) / interval;
    let max_count = limit * interval;
    let page_size = (total_size as f64 / limit as f64).ceil() as u64;
    (0..page_size).map(move |i| {
        let page_start = start + i * max_count;
        let page_end = u64::min(page_start + max_count, end);
        (page_start, page_end)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_merge_adjacent_spans() {
        assert_eq!(
            merge_adjacent_spans(&[(0, 1), (1, 2), (3, 4), (4, 5)]),
            [(0, 2), (3, 5)],
        );
    }

    #[test]
    fn test_generate_missing_spans() {
        assert_eq!(
            generate_missing_spans(0, 5, &[(1, 2), (3, 4)]),
            [(0, 1), (2, 3), (4, 5)],
        );
        assert_eq!(generate_missing_spans(2, 5, &[(1, 3), (4, 6)]), [(3, 4)],);
    }
}

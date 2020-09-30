pub struct Pairwise<I: Iterator> {
    previous: Option<I::Item>,
    underlying: I,
}

impl<I> Iterator for Pairwise<I>
where
    I: Iterator,
    I::Item: Copy,
{
    type Item = (I::Item, I::Item);

    fn next(&mut self) -> Option<Self::Item> {
        let next = self.underlying.next();
        if let (Some(x), Some(y)) = (self.previous, next) {
            self.previous = next;
            return Some((x, y));
        }
        None
    }
}

pub trait IteratorExt: Iterator {
    fn pairwise(mut self) -> Pairwise<Self>
    where
        Self: Sized,
        Self::Item: Copy,
    {
        Pairwise {
            previous: self.next(),
            underlying: self,
        }
    }

    fn minmax<'a>(self) -> (f64, f64)
    where
        Self: Iterator<Item = &'a f64> + Sized,
    {
        let mut min = f64::NAN;
        let mut max = f64::NAN;
        for &value in self {
            min = f64::min(min, value);
            max = f64::max(max, value);
        }
        (min, max)
    }
}

impl<I: Iterator> IteratorExt for I {}

#[cfg(test)]
mod tests {
    use super::IteratorExt;

    #[test]
    fn test_minmax() {
        let vals = [3.0, 1.0, 2.0];
        assert_eq!(vals.iter().minmax(), (1.0, 3.0));
    }

    #[test]
    fn test_pairwise() {
        let input = vec![1, 2, 3];
        let output: Vec<(_, _)> = input.into_iter().pairwise().collect();
        assert_eq!(output, vec![(1, 2), (2, 3)]);
    }

    #[test]
    fn test_pairwise_empty() {
        let input: Vec<u32> = vec![];
        let output: Vec<(_, _)> = input.into_iter().pairwise().collect();
        assert_eq!(output, vec![]);
    }
}

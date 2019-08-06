use std::iter::Chain;
use std::ops::Deref;
use std::slice::{Iter, IterMut};

use rust_decimal::Decimal;

pub fn mean(numbers: &[Decimal]) -> Decimal {
    numbers.iter().sum() / numbers.len()
}

#[derive(Clone, Debug)]
pub struct CircularBuffer<T> {
    data: Vec<T>,
    capacity: usize,
    insertion_index: usize,
}

type CircularBufferIter<'a, T> = Chain<Iter<'a, T>, Iter<'a, T>>;
type CircularBufferIterMut<'a, T> = Chain<IterMut<'a, T>, IterMut<'a, T>>;

impl<T> CircularBuffer<T> {
    #[inline]
    pub fn with_capacity(capacity: usize) -> Self {
        if capacity == 0 {
            panic!("capacity must be greater than 0");
        }

        CircularBuffer {
            data: Vec::with_capacity(capacity),
            capacity,
            insertion_index: 0,
        }
    }

    #[inline]
    pub fn len(&self) -> usize {
        self.data.len()
    }

    #[inline]
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    #[inline]
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    #[inline]
    pub fn clear(&mut self) {
        self.data.clear();
        self.insertion_index = 0;
    }

    pub fn push(&mut self, x: T) {
        if self.data.len() < self.capacity() {
            self.data.push(x);
        } else {
            self.data[self.insertion_index] = x;
        }

        self.insertion_index = (self.insertion_index + 1) % self.capacity();
    }

    #[inline]
    pub fn iter(&self) -> CircularBufferIter<T> {
        let (a, b) = self.data.split_at(self.insertion_index);
        a.iter().chain(b.iter())
    }

    #[inline]
    pub fn iter_mut(&mut self) -> CircularBufferIterMut<T> {
        let (a, b) = self.data.split_at_mut(self.insertion_index);
        a.iter_mut().chain(b.iter_mut())
    }
}

impl<T> Deref for CircularBuffer<T> {
    type Target = [T];

    fn deref(&self) -> &[T] {
        &self.data
    }
}

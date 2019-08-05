// #[derive(Debug)]
// pub struct CircularBuffer<T> where T: Clone {
//     values: Vec<T>,
//     index: usize,
// }

// impl<T> CircularBuffer<T> {
//     pub fn new(size: usize, default: T) -> Self {
//         Self {
//             values: vec![default; size],
//             index: 0,
//         }
//     }

//     pub fn push(self, value: T) {
//         self.values[self.index] = value;
//         self.index = (self.index + 1) % self.values.len();
//     }
// }

// impl<T> IntoIterator for CircularBuffer<T> {
//     type Item = T;
//     type IntoIter = ::std::vec::IntoIter<Self::Item>;

//     fn into_iter(self) -> Self::IntoIter {
//         self.values.into_iter()
//     }
// }

// // impl<T> Iterator for CircularBuffer<T> {
// //     type Item = T;

// //     fn next(&mut self) -> Option<i32> {
// //         self.values.next()
// //     }
// // }

// // impl<T> ExactSizeIterator for CircularBuffer<T> {
// //     fn len(&self) -> usize {
// //         self.values.len()
// //     }
// // }

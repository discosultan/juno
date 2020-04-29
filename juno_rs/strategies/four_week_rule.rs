// use std::cmp::{max, min};

// use crate::{
//     indicators,
//     strategies::{combine, MidTrend, Persistence, Strategy},
//     Advice, Candle,
// };

// pub struct FourWeekRule {
//     prices: VecDeque<f64>,
//     ma: Box<indicators::MA>,
//     t: u32,
// }

// impl FourWeekRule {
//     pub fn new(ma: u32) -> Self {
//         Self {
//             prices: VecDeque::with_capacity(28),
//             ma: ,
//             t: 0,
//         }
//     }
// }

// impl Strategy for FourWeekRule {
//     fn update(&mut self, candle: &Candle) -> Advice {
//         self.macd.update(candle.close);

//         let mut advice = Advice::None;
//         if self.t == self.t1 {
//             if self.macd.value > self.macd.signal {
//                 advice = Advice::Long;
//             } else {
//                 advice = Advice::Short;
//             }

//             advice = combine(
//                 self.mid_trend.update(advice),
//                 self.persistence.update(advice),
//             );
//         }

//         self.t = min(self.t + 1, self.t1);
//         advice
//     }
// }

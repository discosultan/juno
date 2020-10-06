// use std::cmp::{max, min};

// use crate::{
//     indicators::{ma_from_adler32, MA},
//     strategies::{combine, MidTrend, Persistence, Strategy},
//     Advice, Candle,
// };

// #[repr(C)]
// pub struct MAMACXParams {
//     pub short_period: u32,
//     pub long_period: u32,
//     pub neg_threshold: f64,
//     pub pos_threshold: f64,
//     pub persistence: u32,
//     pub short_ma: u32,
//     pub long_ma: u32,
// }

// pub struct MAMACX {
//     short_ma: Box<dyn MA>,
//     long_ma: Box<dyn MA>,
//     neg_threshold: f64,
//     pos_threshold: f64,
//     mid_trend: MidTrend,
//     persistence: Persistence,
//     t: u32,
//     t1: u32,
// }

// impl Strategy for MAMACX {
//     type Params = MAMACXParams;

//     fn new(params: &Self::Params) -> Self {
//         let short_ma = ma_from_adler32(params.short_ma, params.short_period);
//         let long_ma = ma_from_adler32(params.long_ma, params.long_period);
//         let t1 = max(long_ma.maturity(), short_ma.maturity());
//         Self {
//             short_ma,
//             long_ma,
//             mid_trend: MidTrend::new(MidTrend::POLICY_IGNORE),
//             persistence: Persistence::new(params.persistence, false),
//             neg_threshold: params.neg_threshold,
//             pos_threshold: params.pos_threshold,
//             t: 0,
//             t1,
//         }
//     }

//     fn update(&mut self, candle: &Candle) -> Advice {
//         self.short_ma.update(candle.close);
//         self.long_ma.update(candle.close);

//         let mut advice = Advice::None;
//         if self.t == self.t1 {
//             let diff = 100.0 * (self.short_ma.value() - self.long_ma.value())
//                 / ((self.short_ma.value() + self.long_ma.value()) / 2.0);

//             if diff > self.pos_threshold {
//                 advice = Advice::Long;
//             } else if diff < self.neg_threshold {
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

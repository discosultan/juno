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

#[derive(Clone, Copy, PartialEq)]
pub enum Advice {
    None,
    Buy,
    Sell,
}

#[derive(Debug)]
pub struct Candle {
    pub time: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Debug)]
pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

impl Fees {
    pub fn none() -> Self {
        Fees {
            maker: 0.0,
            taker: 0.0,
        }
    }
}

#[derive(Clone, Copy, PartialEq)]
pub enum Trend {
    Unknown,
    Up,
    Down,
}

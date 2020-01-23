#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Advice {
    Buy,
    Sell,
}

#[derive(Debug, Clone, Copy)]
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

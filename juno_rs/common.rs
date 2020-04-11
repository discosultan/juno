#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Advice {
    None,
    Long,
    Short,
}

#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct Candle {
    pub time: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Debug)]
#[repr(C)]
pub struct Fees {
    pub maker: f64,
    pub taker: f64,
}

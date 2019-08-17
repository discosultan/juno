use crate::{Candle, Fees, Filters};

pub struct Position {
    time: u64,
    total_quote: f64,
    closing_time: u64,
    closing_total_quote: f64,
}

impl Position {
    pub fn new(time: u64, total_quote: f64) -> Self {
        Self {
            time,
            total_quote,
            closing_time: 0,
            closing_total_quote: 0.0,
        }
    }

    pub fn close(&mut self, time: u64, total_quote: f64) {
        self.closing_time = time;
        self.closing_total_quote = total_quote;
    }

    pub fn duration(&self) -> u64 {
        self.closing_time - self.time
    }

    pub fn cost(&self) -> f64 {
        self.total_quote
    }

    pub fn gain(&self) -> f64 {
        self.total_quote - self.closing_total_quote
    }

    pub fn profit(&self) -> f64 {
        self.gain() - self.cost()
    }

    pub fn roi(&self) -> f64 {
        self.profit() / self.cost()
    }

    pub fn annualized_roi(&self) -> f64 {
        let n = self.duration() as f64 / 31_556_952_000.0;
        (1.0 + self.roi()).powf(1.0 / n) - 1.0
    }
}

pub struct TradingSummary<'a> {
    quote: f64,
    fees: &'a Fees,
    filters: &'a Filters,

    positions: Vec<Position>,
    first_candle: Option<&'a Candle>,
    last_candle: Option<&'a Candle>,
}

impl<'a> TradingSummary<'a> {
    pub fn new(quote: f64, fees: &'a Fees, filters: &'a Filters) -> Self {
        Self {
            quote,
            fees,
            filters,
            positions: Vec::new(),
            first_candle: None,
            last_candle: None,
        }
    }

    pub fn append_candle(&self, _candle: &Candle) {

    }

    pub fn append_position(&self, _pos: Position) {

    }
}

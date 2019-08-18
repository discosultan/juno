use crate::{Candle, Fees, Filters};

const YEAR_MS: f64 = 31_556_952_000.0;

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
        let n = self.duration() as f64 / YEAR_MS;
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

    pub fn append_candle(&mut self, candle: &'a Candle) {
        if self.first_candle.is_none() {
            self.first_candle = Some(candle);
        }
        self.last_candle = Some(candle);
    }

    pub fn append_position(&mut self, pos: Position) {
        self.positions.push(pos);
    }

    pub fn cost(&self) -> f64 {
        self.quote
    }

    pub fn gain(&self) -> f64 {
        self.quote + self.profit()
    }

    pub fn profit(&self) -> f64 {
        self.positions.iter().map(|p| p.profit()).sum()
    }

    pub fn roi(&self) -> f64 {
        self.profit() / self.cost()
    }

    pub fn annualized_roi(&self) -> f64 {
        // let n = self
        0.0
    }
}

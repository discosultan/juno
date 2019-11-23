use crate::{Candle, Fees, Filters, Strategy};

const YEAR_MS: f64 = 31_556_952_000.0;

#[derive(Debug)]
pub struct Position {
    time: u64,
    pub price: f64,
    pub size: f64,
    pub cost: f64,
    pub fee: f64,

    // Calculated.
    pub duration: u64,
    pub gain: f64,
    pub profit: f64,
    pub roi: f64,
    pub annualized_roi: f64,
}

impl Position {
    pub fn new(time: u64, price: f64, size: f64, fee: f64) -> Self {
        Self {
            time,
            price,
            size,
            cost: price * size,
            fee,
            duration: 0,
            gain: 0.0,
            profit: 0.0,
            roi: 0.0,
            annualized_roi: 0.0,
        }
    }

    pub fn close(&mut self, time: u64, price: f64, size: f64, fee: f64) {
        self.duration = time - self.time;
        self.gain = price * size - fee;
        self.profit = self.gain - self.cost;
        self.roi = self.profit / self.cost;

        // Annualized ROI.
        let n = self.duration as f64 / YEAR_MS;
        self.annualized_roi = (1.0 + self.roi).powf(1.0 / n) - 1.0;
    }
}

#[derive(Debug)]
pub struct TradingSummary<'a> {
    fees: &'a Fees,
    filters: &'a Filters,

    positions: Vec<Position>,
    first_candle: Option<&'a Candle>,
    last_candle: Option<&'a Candle>,

    duration: u64,
    cost: f64,

    // Calculated.
    pub gain: f64,
    pub profit: f64,
    pub roi: f64,
    pub annualized_roi: f64,
    pub mean_position_profit: f64,
    pub mean_position_duration: u64,
    pub drawdowns: Vec<f64>,
    pub max_drawdown: f64,
    pub mean_drawdown: f64,
    pub num_positions: u32,
    pub num_positions_in_profit: u32,
    pub num_positions_in_loss: u32,
}

impl<'a> TradingSummary<'a> {
    pub fn new(start: u64, end: u64, quote: f64, fees: &'a Fees, filters: &'a Filters) -> Self {
        Self {
            fees,
            filters,
            positions: Vec::new(),
            first_candle: None,
            last_candle: None,
            duration: end - start,
            cost: quote,
            gain: 0.0,
            profit: 0.0,
            roi: 0.0,
            annualized_roi: 0.0,
            mean_position_profit: 0.0,
            mean_position_duration: 0,
            drawdowns: Vec::new(),
            max_drawdown: 0.0,
            mean_drawdown: 0.0,
            num_positions: 0,
            num_positions_in_profit: 0,
            num_positions_in_loss: 0,
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

    pub fn calculate(&mut self) {
        let mut quote = self.cost;
        let mut max_quote = quote;
        self.max_drawdown = 0.0;
        self.drawdowns.resize(self.positions.len() + 1, 0.0);
        self.drawdowns[0] = 0.0;

        for (i, pos) in self.positions.iter().enumerate() {
            self.profit += pos.profit;

            if pos.profit >= 0.0 {
                self.num_positions_in_profit += 1;
            } else {
                self.num_positions_in_loss += 1;
            }

            self.mean_position_profit += pos.profit;
            self.mean_position_duration += pos.duration;

            quote += pos.profit;
            max_quote = f64::max(max_quote, quote);
            let drawdown = 1.0 - quote / max_quote;
            self.drawdowns[i + 1] = drawdown;
            self.mean_drawdown += drawdown;
            self.max_drawdown = f64::max(self.max_drawdown, drawdown);
        }

        self.num_positions = self.positions.len() as u32;
        if self.num_positions > 0 {
            self.mean_position_profit /= self.num_positions as f64;
            self.mean_position_duration /= self.num_positions as u64;
            self.mean_drawdown /= self.drawdowns.len() as f64;
        }

        self.gain = self.cost + self.profit;
        self.roi = self.profit / self.cost;

        // Annualized ROI.
        let n = self.duration as f64 / YEAR_MS;
        if n == 0.0 {
            self.annualized_roi = 0.0;
        } else {
            self.annualized_roi = (1.0 + self.roi).powf(1.0 / n) - 1.0;
        }
    }
}

pub struct TradingContext<T: Strategy> {
    pub strategy: T,
    pub quote: f64,
    pub open_position: Option<Position>,
    pub last_candle: Option<Candle>,
    pub highest_close_since_position: f64,

}

impl<T: Strategy> TradingContext<T> {
    pub fn new(strategy: T, quote: f64) -> Self {
        Self {
            strategy,
            quote,
            open_position: None,
            last_candle: None,
            highest_close_since_position: 0.0,
        }
    }
}

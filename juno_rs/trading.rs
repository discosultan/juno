use crate::Candle;

const YEAR_MS: f64 = 31_556_952_000.0;


pub struct StopLoss {
    pub threshold: f64,
    trail: bool,
    highest_close_since_position: f64,
    lowest_close_since_position: f64,
    close: f64,
}

impl StopLoss {
    pub fn new(threshold: f64, trail: bool) -> Self {
        Self {
            threshold,
            trail,
            highest_close_since_position: 0.0,
            lowest_close_since_position: f64::MAX,
            close: 0.0,
        }
    }

    pub fn upside_hit(&self) -> bool {
        self.threshold == 0.0
        || self.close >= self.highest_close_since_position * (1.0 - self.threshold)
    }

    pub fn downside_hit(&self) -> bool {
        self.threshold == 0.0
        || self.close <= self.lowest_close_since_position * (1.0 + self.threshold)
    }

    pub fn clear(&mut self, candle: &Candle) {
        self.highest_close_since_position = candle.close;
        self.lowest_close_since_position = candle.close;
    }

    pub fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
        self.highest_close_since_position = f64::max(
            self.highest_close_since_position, candle.close
        );
        self.lowest_close_since_position = f64::min(
            self.lowest_close_since_position, candle.close
        );
    }
}


pub struct TakeProfit {
    pub threshold: f64,
    close_at_position: f64,
    close: f64,
}

impl TakeProfit {
    pub fn new(threshold: f64) -> Self {
        Self {
            threshold,
            close_at_position: 0.0,
            close: 0.0,
        }
    }

    pub fn upside_hit(&self) -> bool {
        self.threshold == 0.0 || self.close >= self.close_at_position * (1.0 + self.threshold)
    }

    pub fn downside_hit(&self) -> bool {
        self.threshold == 0.0 || self.close <= self.close_at_position * (1.0 - self.threshold)
    }

    pub fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
    }

    pub fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
    }
}


#[derive(Debug)]
pub struct LongPosition {
    pub time: u64,
    pub price: f64,
    pub cost: f64,
    pub base_gain: f64,
    pub base_cost: f64,

    pub close_time: u64,
    pub duration: u64,
    pub gain: f64,
    pub profit: f64,
    pub roi: f64,
    pub annualized_roi: f64,
}

impl LongPosition {
    pub fn new(time: u64, price: f64, size: f64, quote: f64, fee: f64) -> Self {
        Self {
            time,
            price,
            cost: quote,
            base_gain: size - fee,

            base_cost: 0.0,
            close_time: 0,
            duration: 0,
            gain: 0.0,
            profit: 0.0,
            roi: 0.0,
            annualized_roi: 0.0,
        }
    }

    pub fn close(&mut self, time: u64, _price: f64, size: f64, quote: f64, fee: f64) {
        self.close_time = time;
        self.duration = time - self.time;
        self.base_cost = size;
        self.gain = quote - fee;
        self.profit = self.gain - self.cost;
        self.roi = self.profit / self.cost;
        self.annualized_roi = annualized_roi(self.duration, self.roi);
    }
}

#[derive(Debug)]
pub struct ShortPosition {
    pub time: u64,
    pub collateral: f64,
    pub borrowed: f64,
    pub price: f64,
    pub quote: f64,
    pub fee: f64,
    pub cost: f64,
    pub base_gain: f64,
    pub base_cost: f64,

    pub close_time: u64,
    pub interest: f64,
    pub duration: u64,
    pub gain: f64,
    pub profit: f64,
    pub roi: f64,
    pub annualized_roi: f64,
}

impl ShortPosition {
    pub fn new(
        time: u64,
        collateral: f64,
        borrowed: f64,
        price: f64,
        _size: f64,
        quote: f64,
        fee: f64,
    ) -> Self {
        Self {
            time,
            collateral,
            borrowed,
            price,
            quote,
            fee,
            cost: collateral,
            base_gain: borrowed,

            base_cost: borrowed,
            close_time: 0,
            interest: 0.0,
            duration: 0,
            gain: 0.0,
            profit: 0.0,
            roi: 0.0,
            annualized_roi: 0.0,
        }
    }

    pub fn close(
        &mut self,
        interest: f64,
        time: u64,
        _price: f64,
        _size: f64,
        quote: f64,
        _fee: f64,
    ) {
        self.interest = interest;
        self.close_time = time;
        self.duration = time - self.time;
        self.gain = self.quote - self.fee + self.collateral - quote;
        self.profit = self.gain - self.cost;
        self.roi = self.profit / self.cost;
        self.annualized_roi = annualized_roi(self.duration, self.roi);
    }
}

#[derive(Debug)]
pub struct TradingSummary {
    pub long_positions: Vec<LongPosition>,
    pub short_positions: Vec<ShortPosition>,

    pub interval: u64,
    pub start: u64,
    pub end: u64,
    pub duration: u64,
    pub cost: f64,

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

impl TradingSummary {
    pub fn new(interval: u64, start: u64, end: u64, quote: f64) -> Self {
        Self {
            long_positions: Vec::new(),
            short_positions: Vec::new(),
            interval,
            start,
            end,
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

    pub fn append_long_position(&mut self, pos: LongPosition) {
        self.long_positions.push(pos);
    }

    pub fn append_short_position(&mut self, pos: ShortPosition) {
        self.short_positions.push(pos);
    }

    pub fn calculate(&mut self) {
        let mut quote = self.cost;
        let mut max_quote = quote;
        self.num_positions = self.long_positions.len() as u32 + self.short_positions.len() as u32;
        self.max_drawdown = 0.0;
        self.drawdowns.resize(self.num_positions as usize + 1, 0.0);
        self.drawdowns[0] = 0.0;

        let long_pos = self
            .long_positions
            .iter()
            .map(|pos| (pos.profit, pos.duration));
        let short_pos = self
            .short_positions
            .iter()
            .map(|pos| (pos.profit, pos.duration));

        for (i, (profit, duration)) in long_pos.chain(short_pos).enumerate() {
            self.profit += profit;

            if profit >= 0.0 {
                self.num_positions_in_profit += 1;
            } else {
                self.num_positions_in_loss += 1;
            }

            self.mean_position_profit += profit;
            self.mean_position_duration += duration;

            quote += profit;
            max_quote = f64::max(max_quote, quote);
            let drawdown = 1.0 - quote / max_quote;
            self.drawdowns[i + 1] = drawdown;
            self.mean_drawdown += drawdown;
            self.max_drawdown = f64::max(self.max_drawdown, drawdown);
        }

        if self.num_positions > 0 {
            self.mean_position_profit /= self.num_positions as f64;
            self.mean_position_duration /= self.num_positions as u64;
            self.mean_drawdown /= self.drawdowns.len() as f64;
        }

        self.gain = self.cost + self.profit;
        self.roi = self.profit / self.cost;
        self.annualized_roi = annualized_roi(self.duration, self.roi);
    }
}

fn annualized_roi(duration: u64, roi: f64) -> f64 {
    let n = duration as f64 / YEAR_MS;
    if n == 0.0 {
        0.0
    } else {
        (1.0 + roi).powf(1.0 / n) - 1.0
    }
}

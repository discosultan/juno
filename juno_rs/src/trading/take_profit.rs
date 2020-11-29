use crate::Candle;

pub trait TakeProfitRenameMe {
    fn upside_hit(&self) -> bool {
        false
    }

    fn downside_hit(&self) -> bool {
        false
    }

    fn clear(&mut self, _candle: &Candle) {}

    fn update(&mut self, _candle: &Candle) {}
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
}

impl TakeProfitRenameMe for TakeProfit {
    fn upside_hit(&self) -> bool {
        self.threshold > 0.0 && self.close >= self.close_at_position * (1.0 + self.threshold)
    }

    fn downside_hit(&self) -> bool {
        self.threshold > 0.0 && self.close <= self.close_at_position * (1.0 - self.threshold)
    }

    fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
    }
}

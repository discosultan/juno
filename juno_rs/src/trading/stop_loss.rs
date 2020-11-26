use crate::Candle;

pub trait StopLossRenameMe {
    fn upside_hit(&self) -> bool {
        false
    }

    fn downside_hit(&self) -> bool {
        false
    }

    fn clear(&mut self, _candle: &Candle) {}

    fn update(&mut self, _candle: &Candle) {}
}

pub struct StopLoss {
    pub threshold: f64,
    trail: bool,
    close_at_position: f64,
    highest_close_since_position: f64,
    lowest_close_since_position: f64,
    close: f64,
}

impl StopLoss {
    pub fn new(threshold: f64, trail: bool) -> Self {
        Self {
            threshold,
            trail,
            close_at_position: 0.0,
            highest_close_since_position: 0.0,
            lowest_close_since_position: f64::MAX,
            close: 0.0,
        }
    }
}

impl StopLossRenameMe for StopLoss {
    fn upside_hit(&self) -> bool {
        self.threshold > 0.0
            && self.close
                <= if self.trail {
                    self.highest_close_since_position
                } else {
                    self.close_at_position
                } * (1.0 - self.threshold)
    }

    fn downside_hit(&self) -> bool {
        self.threshold > 0.0
            && self.close
                >= if self.trail {
                    self.lowest_close_since_position
                } else {
                    self.close_at_position
                } * (1.0 + self.threshold)
    }

    fn clear(&mut self, candle: &Candle) {
        self.close_at_position = candle.close;
        self.highest_close_since_position = candle.close;
        self.lowest_close_since_position = candle.close;
    }

    fn update(&mut self, candle: &Candle) {
        self.close = candle.close;
        self.highest_close_since_position =
            f64::max(self.highest_close_since_position, candle.close);
        self.lowest_close_since_position = f64::min(self.lowest_close_since_position, candle.close);
    }
}

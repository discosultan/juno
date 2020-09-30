use std::cmp::min;

pub struct DM {
    pub plus_value: f64,
    pub minus_value: f64,
    per: f64,
    dmup: f64,
    dmdown: f64,
    prev_high: f64,
    prev_low: f64,
    t: u32,
    t1: u32,
    t2: u32,
    t3: u32,
}

impl DM {
    pub fn new(period: u32) -> Self {
        Self {
            plus_value: 0.0,
            minus_value: 0.0,
            dmup: 0.0,
            dmdown: 0.0,
            per: f64::from(period - 1) / f64::from(period),
            prev_high: 0.0,
            prev_low: 0.0,
            t: 0,
            t1: 1,
            t2: period - 1,
            t3: period,
        }
    }

    pub fn maturity(&self) -> u32 {
        self.t2
    }

    pub fn mature(&self) -> bool {
        self.t >= self.t2
    }

    pub fn update(&mut self, high: f64, low: f64) {
        if self.t >= self.t1 && self.t < self.t2 {
            let (dp, dm) = calc_direction(self.prev_high, self.prev_low, high, low);
            self.dmup += dp;
            self.dmdown += dm;
        }

        if self.t == self.t2 {
            self.plus_value = self.dmup;
            self.minus_value = self.dmdown;
        } else if self.t == self.t3 {
            let (dp, dm) = calc_direction(self.prev_high, self.prev_low, high, low);
            self.dmup = self.dmup * self.per + dp;
            self.dmdown = self.dmdown * self.per + dm;
            self.plus_value = self.dmup;
            self.minus_value = self.dmdown;
        }

        self.prev_high = high;
        self.prev_low = low;
        self.t = min(self.t + 1, self.t3);
    }
}

fn calc_direction(prev_high: f64, prev_low: f64, high: f64, low: f64) -> (f64, f64) {
    let mut up = high - prev_high;
    let mut down = prev_low - low;

    if up < 0.0 {
        up = 0.0;
    } else if up > down {
        down = 0.0;
    }

    if down < 0.0 {
        down = 0.0;
    } else if down > up {
        up = 0.0;
    }

    (up, down)
}

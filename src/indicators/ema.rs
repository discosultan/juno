pub struct Ema {
    pub value: f64,
    a: f64,
    t: u32,
}

impl Ema {
    pub fn new(period: u32) -> Self {
        Self::with_smoothing(2.0 / f64::from(period + 1))
    }

    pub fn req_history(&self) -> u32 {
        0
    }

    pub fn update(&mut self, price: f64) {
        self.value = match self.t {
            0 => {
                self.t = 1;
                price
            }
            _ => (price - self.value) * self.a + self.value,
        };
    }

    pub fn with_smoothing(a: f64) -> Self {
        Self {
            value: 0.0,
            a,
            t: 0,
        }
    }
}

use super::dx::DX;
use super::smma::Smma;

pub struct Adx {
    pub value: f64,
    dx: DX,
    smma: Smma,
}

impl Adx {
    pub fn new(period: u32) -> Self {
        Self {
            value: 0.0,
            dx: DX::new(period),
            smma: Smma::new(period),
        }
    }

    pub fn update(&mut self, high: f64, low: f64, close: f64) {
        self.dx.update(high, low, close);
        self.smma.update(self.dx.value);
        self.value = self.smma.value;
    }
}

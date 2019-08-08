use std::cmp::min;

pub struct Sma {
    pub value: f64,
    inputs: Vec<f64>,
    i: usize,
    sum: f64,

    t: u32,
    t1: u32,
}

impl Sma {
    pub fn new(period: u32) -> Self {
        Self {
            inputs: vec![0.0; period as usize],
            i: 0,
            sum: 0.0,
            t: 0,
            t1: period - 1,
        }
    }

    pub fn req_history(&self) -> u32 {
        self.t1
    }

    pub fn update(&mut self, input: f64) {
        let last = self.inputs[self.i];
        self.inputs[self.i] = input;
        self.i = (self.i + 1) % self.inputs.len();
        self.sum = self.sum - last + input;
        self.value = self.sum / self.inputs.len() as f64;

        self.t = min(self.t + 1, self.t1);
    }
}

#[derive(Debug)]
#[repr(C)]
pub struct Price {
    pub min: f64,
    pub max: f64,
    pub step: f64,
}

impl Price {
    pub fn round_down(&self, price: f64) -> f64 {
        let mut price = price;
        if price < self.min {
            return 0.0;
        }
        if self.max > 0.0 {
            price = f64::min(price, self.max);
        }
        if self.step > 0.0 {
            (price / self.step).floor() * self.step
        } else {
            price
        }
    }

    pub fn valid(&self, price: f64) -> bool {
        ((self.min == 0.0 || price >= self.min)
            && (self.max == 0.0 || price <= self.max)
            && (self.step == 0.0 || (price - self.min) % self.step == 0.0))
    }
}

#[derive(Debug)]
#[repr(C)]
pub struct Size {
    pub min: f64,
    pub max: f64,
    pub step: f64,
}

impl Size {
    pub fn round_down(&self, size: f64) -> f64 {
        let mut size = size;
        if size < self.min {
            return 0.0;
        }
        size = f64::min(size, self.max);
        if self.step > 0.0 {
            (size / self.step).floor() * self.step
        } else {
            size
        }
    }

    pub fn round_up(&self, size: f64) -> f64 {
        let mut size = size;
        if size < self.min {
            return 0.0;
        }
        size = f64::min(size, self.max);
        (size / self.step).ceil() * self.step
    }

    pub fn valid(&self, size: f64) -> bool {
        size >= self.min && size <= self.max && (size - self.min) % self.step == 0.0
    }
}

#[derive(Debug)]
#[repr(C)]
pub struct Filters {
    pub price: Price,
    pub size: Size,

    pub base_precision: u32,
    pub quote_precision: u32,
}

#[derive(Debug)]
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
        (price / self.step).floor() * self.step
    }

    pub fn valid(&self, price: f64) -> bool {
        ((self.min == 0.0 || price >= self.min)
            && (self.max == 0.0 || price <= self.max)
            && (self.step == 0.0 || (price - self.min) % self.step == 0.0))
    }

    pub fn none() -> Self {
        Price {
            min: 0.0,
            max: 0.0,
            step: 0.0,
        }
    }
}

#[derive(Debug)]
pub struct Size {
    min: f64,
    max: f64,
    step: f64,
}

impl Size {
    pub fn round_down(&self, size: f64) -> f64 {
        let mut size = size;
        if size < self.min {
            return 0.0;
        }
        size = f64::min(size, self.max);
        (size / self.step).floor() * self.step
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

    pub fn none() -> Self {
        Size {
            min: 0.0,
            max: 0.0,
            step: 0.0,
        }
    }
}

#[derive(Debug)]
pub struct Filters {
    pub price: Price,
    pub size: Size,
}

impl Filters {
    pub fn none() -> Self {
        Filters {
            price: Price::none(),
            size: Size::none(),
        }
    }
}

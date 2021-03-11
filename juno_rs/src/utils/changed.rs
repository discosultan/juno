use crate::Advice;

pub struct Changed {
    enabled: bool,
    previous: Advice,
    age: u32,
}

impl Changed {
    pub fn new(enabled: bool) -> Self {
        Self {
            enabled,
            previous: Advice::None,
            age: 0,
        }
    }

    pub fn prevailing_advice(&self) -> Advice {
        return self.previous
    }

    pub fn prevailing_advice_age(&self) -> u32 {
        return self.age
    }

    pub fn maturity(&self) -> u32 {
        1
    }

    pub fn update(&mut self, value: Advice) -> Advice {
        if !self.enabled {
            return value;
        }

        if value == Advice::None || value == self.previous {
            self.age += 1;
            Advice::None
        } else {
            self.previous = value;
            self.age = 1;
            value
        }
    }
}

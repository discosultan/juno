use crate::Trend;

pub struct Persistence {
    age: u32,
    level: u32,
    allow_next_trend: bool,
    trend: Trend,
    potential_trend: Trend,
}

impl Persistence {
    pub fn new(level: u32, allow_initial: bool) -> Self {
        Persistence {
            age: 0,
            level,
            allow_next_trend: allow_initial,
            trend: Trend::Unknown,
            potential_trend: Trend::Unknown,
        }
    }

    pub fn update(&mut self, trend: Trend) -> (Trend, bool) {
        let mut trend_changed = false;

        if trend == Trend::Unknown
            || (self.potential_trend != Trend::Unknown && trend != self.potential_trend)
        {
            self.allow_next_trend = true;
        }

        if trend != self.potential_trend {
            self.age = 0;
            self.potential_trend = trend;
        }

        if self.allow_next_trend && self.age == self.level && self.potential_trend != self.trend {
            self.trend = self.potential_trend;
            trend_changed = true;
        }

        self.age += 1;

        (self.trend, trend_changed)
    }
}

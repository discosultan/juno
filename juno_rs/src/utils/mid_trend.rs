use rand::prelude::*;
use serde::{Deserialize, Serialize};

use crate::Advice;

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
pub enum MidTrendPolicy {
    Current,
    Previous,
    Ignore,
}

const MID_TREND_POLICY_CHOICES: [MidTrendPolicy; 3] = [
    MidTrendPolicy::Current,
    MidTrendPolicy::Previous,
    MidTrendPolicy::Ignore,
];

pub struct MidTrend {
    policy: MidTrendPolicy,
    previous: Option<Advice>,
    enabled: bool,
}

impl MidTrend {
    pub fn new(policy: MidTrendPolicy) -> Self {
        Self {
            policy,
            previous: None,
            enabled: true,
        }
    }

    pub fn maturity(&self) -> u32 {
        if self.policy == MidTrendPolicy::Current {
            1
        } else {
            2
        }
    }

    pub fn update(&mut self, value: Advice) -> Advice {
        if !self.enabled || self.policy != MidTrendPolicy::Ignore {
            return value;
        }

        let mut result = Advice::None;
        if self.previous.is_none() {
            self.previous = Some(value)
        } else if Some(value) != self.previous {
            self.enabled = false;
            result = value;
        }
        result
    }
}

pub trait MidTrendPolicyExt {
    fn gen_mid_trend_policy(&mut self) -> MidTrendPolicy;
}

impl MidTrendPolicyExt for StdRng {
    fn gen_mid_trend_policy(&mut self) -> MidTrendPolicy {
        *MID_TREND_POLICY_CHOICES.choose(self).unwrap()
    }
}

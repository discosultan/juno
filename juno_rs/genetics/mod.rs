use crate::{indicators::adler32, strategies::MidTrend};
use rand::{Rng, SeedableRng, rngs::StdRng};
use std::iter;

pub trait Chromosome {
    fn generate(rng: &mut StdRng) -> Self;
}

struct Individual<T: Chromosome> {
    trader: TraderParams,
    strategy: T,
}

struct TraderParams {
    pub missed_candle_policy: u32,
    pub stop_loss: f64,
    pub trail_stop_loss: bool,
    pub take_profit: f64,
}

impl Chromosome for TraderParams {
    fn generate(rng: &mut StdRng) -> Self {
        Self {
            missed_candle_policy: rng.gen_range(0, 3),
            stop_loss: if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 0.9999) },
            trail_stop_loss: rng.gen_bool(0.5),
            take_profit: if rng.gen_bool(0.5) { 0.0 } else { rng.gen_range(0.0001, 9.9999) },
        }
    }
}

struct FourWeekRuleParams {
    pub period: u32,
    pub ma: u32,
    pub ma_period: u32,
    pub mid_trend_policy: u32,
}

const MA_CHOICES: [u32; 7] = [
    adler32::ALMA,
    adler32::EMA,
    adler32::EMA2,
    adler32::SMA,
    adler32::SMMA,
    adler32::DEMA,
    adler32::KAMA,
];

impl Chromosome for FourWeekRuleParams {
    fn generate(rng: &mut StdRng) -> Self {
        Self {
            period: rng.gen_range(2, 100),
            ma: MA_CHOICES[rng.gen_range(0, MA_CHOICES.len())],
            ma_period: rng.gen_range(2, 100),
            mid_trend_policy: MidTrend::POLICY_IGNORE,
        }
    }
}

pub fn run<T: Chromosome>() {
    let population_size = 100;
    let generations = 10;
    let seed = 1;

    let mut rng = StdRng::seed_from_u64(seed);

    let population: Vec<Individual<T>> = iter::repeat(population_size)
        .map(|_| Individual {
            trader: TraderParams::generate(&mut rng),
            strategy: T::generate(&mut rng)
        })
        .collect();
}

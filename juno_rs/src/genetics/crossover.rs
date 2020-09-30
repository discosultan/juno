use super::Chromosome;
use rand::prelude::*;

pub trait Crossover {
    fn cross<T: Chromosome>(&self, rng: &mut StdRng, chromosome1: &mut T, chromosome2: &mut T);
}

pub struct UniformCrossover {
    mix_probability: f32,
}

impl UniformCrossover {
    pub fn new(mix_probability: f32) -> Self {
        assert!(0.0 <= mix_probability && mix_probability <= 1.0);
        Self {
            mix_probability,
        }
    }
}

impl Default for UniformCrossover {
    fn default() -> Self {
        Self {
            mix_probability: 0.5,
        }
    }
}

impl Crossover for UniformCrossover {
    fn cross<T: Chromosome>(&self, rng: &mut StdRng, chromosome1: &mut T, chromosome2: &mut T) {
        for i in 0..T::len() {
            if rng.gen::<f32>() < self.mix_probability {
                chromosome1.cross(chromosome2, i);
            }
        }
    }
}

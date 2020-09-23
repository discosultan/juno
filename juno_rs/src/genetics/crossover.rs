use rand::{Rng, rngs::StdRng};
use super::{Chromosome, Individual};

pub trait Crossover {
    fn cross<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        parent1: &Individual<T>,
        parent2: &Individual<T>,
    ) -> (Individual<T>, Individual<T>);
}

pub struct UniformCrossover {
    mix_probability: f32,
}

impl Default for UniformCrossover {
    fn default() -> Self {
        Self {
            mix_probability: 0.5,
        }
    }
}

impl Crossover for UniformCrossover {
    fn cross<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        parent1: &Individual<T>,
        parent2: &Individual<T>,
    ) -> (Individual<T>, Individual<T>) {
        let mut child1 = parent1.clone();
        let mut child2 = parent2.clone();

        for i in 0..Individual::<T>::len() {
            if rng.gen::<f32>() < self.mix_probability {
                child1.cross(parent2, i);
                child2.cross(parent1, i);
            }
        }

        (child1, child2)
    }
}

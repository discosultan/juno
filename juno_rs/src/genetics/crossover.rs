use rand::{Rng, rngs::StdRng};
use super::Chromosome;

pub trait Crossover {
    fn cross<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        chromosome1: &mut T,
        chromosome2: &mut T,
    );
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
        chromosome1: &mut T,
        chromosome2: &mut T,
    ) {
        // let mut child1 = parent1.clone();
        // let mut child2 = parent2.clone();

        for i in 0..T::len() {
            if rng.gen::<f32>() < self.mix_probability {
                chromosome1.cross(chromosome2, i);
                // chromosome2.cross(chromosome1, i);
            }
        }

        // (child1, child2)
    }
}

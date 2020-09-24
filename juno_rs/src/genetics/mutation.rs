use super::Chromosome;
use rand::{rngs::StdRng, Rng};

pub trait Mutation {
    fn mutate<T: Chromosome>(&self, rng: &mut StdRng, chromosome: &mut T);
}

pub struct UniformMutation {
    mutation_probability: f32,
}

impl Default for UniformMutation {
    fn default() -> Self {
        Self {
            mutation_probability: 0.1,
        }
    }
}

impl Mutation for UniformMutation {
    fn mutate<T: Chromosome>(&self, rng: &mut StdRng, chromosome: &mut T) {
        for i in 0..T::len() {
            if rng.gen::<f32>() < self.mutation_probability {
                chromosome.mutate(rng, i);
            }
        }
    }
}

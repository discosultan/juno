use super::Chromosome;
use rand::prelude::*;

pub trait Mutation {
    fn mutate<T: Chromosome>(&self, rng: &mut StdRng, chromosome: &mut T, ctx: &T::Context);
}

pub struct UniformMutation {
    mutation_probability: f32,
}

impl UniformMutation {
    pub fn new(mutation_probability: f32) -> Self {
        assert!(0.0 <= mutation_probability && mutation_probability <= 1.0);
        UniformMutation {
            mutation_probability,
        }
    }
}

impl Default for UniformMutation {
    fn default() -> Self {
        Self {
            mutation_probability: 0.1,
        }
    }
}

impl Mutation for UniformMutation {
    fn mutate<T: Chromosome>(&self, rng: &mut StdRng, chromosome: &mut T, ctx: &T::Context) {
        for i in 0..T::len() {
            if rng.gen::<f32>() < self.mutation_probability {
                chromosome.mutate(rng, i, ctx);
            }
        }
    }
}

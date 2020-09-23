use rand::{Rng, rngs::StdRng};
use super::{Chromosome, Individual};

pub trait Mutation {
    fn mutate<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        ind: &mut Individual<T>,
    );
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
    fn mutate<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        ind: &mut Individual<T>,
    ) {
        for i in 0..Individual::<T>::len() {
            if rng.gen::<f32>() < self.mutation_probability {
                ind.mutate(rng, i);
            }
        }
    }
}

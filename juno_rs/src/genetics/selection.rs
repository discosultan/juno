use super::{Chromosome, Individual};
use rand::prelude::*;

pub trait Selection {
    fn select<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        rate: f32,
    );
}

#[derive(Default)]
pub struct EliteSelection {
    shuffle: bool, // TODO: Does it make sense?
}

impl Selection for EliteSelection {
    fn select<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        rate: f32,
    ) {
        assert!(rate <= 1.0);

        // Assumes parents are ordered by fitness desc.
        let count = (parents.len() as f32 * rate) as usize;
        offsprings.extend_from_slice(&parents[0..count]);

        if self.shuffle {
            offsprings.shuffle(rng);
        }
    }
}

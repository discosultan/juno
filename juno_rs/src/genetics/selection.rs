use super::{Chromosome, Individual};

pub trait Selection {
    fn select<T: Chromosome>(
        &self, parents: &[Individual<T>], offsprings: &mut Vec<Individual<T>>, count: usize
    );
}

pub struct EliteSelection;

impl Selection for EliteSelection {
    fn select<T: Chromosome>(
        &self, parents: &[Individual<T>], offsprings: &mut Vec<Individual<T>>, count: usize
    ) {
        offsprings.extend_from_slice(&parents[0..count]);
    }
}

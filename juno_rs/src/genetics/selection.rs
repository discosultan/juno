use super::{Chromosome, Individual};

pub trait Selection {
    fn select<T: Chromosome>(
        &self, population: &[Individual<T>], fitnesses: &[f64], count: usize
    ) -> Vec<Individual<T>>;
}

pub struct EliteSelection;

impl Selection for EliteSelection {
    fn select<T: Chromosome>(
        &self, population: &[Individual<T>], fitnesses: &[f64], count: usize
    ) -> Vec<Individual<T>> {
        let mut fitness_copies: Vec<(usize, f64)> = fitnesses.iter().cloned().enumerate().collect();
        fitness_copies.sort_by(|(_, a), (_, b)| b.partial_cmp(a).unwrap());
        fitness_copies
            .iter()
            .take(count)
            .map(|(i, _)| population[*i].clone())
            .collect()
    }
}

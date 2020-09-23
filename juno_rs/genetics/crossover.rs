use super::{Chromosome, Individual};

pub trait Crossover {
    fn cross<T: Chromosome>(
        &self, parent1: &Individual<T>, parent2: &Individual<T>
    ) -> (Individual<T>, Individual<T>);
}

pub struct UniformCrossover;

impl Crossover for UniformCrossover {
    fn cross<T: Chromosome>(
        &self, parent1: &Individual<T>, parent2: &Individual<T>
    ) -> (Individual<T>, Individual<T>) {
        let mut child1 = parent1.clone();
        let mut child2 = parent2.clone();
        
        (child1, child2)
    }
}

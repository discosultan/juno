pub mod algorithm;
pub mod crossover;
pub mod mutation;
pub mod reinsertion;
pub mod selection;

pub use algorithm::GeneticAlgorithm;

use juno_derive_rs::*;
use rand::prelude::*;
use serde::Serialize;
use std::{cmp::Ordering, fmt::Debug};

pub trait Chromosome: Clone + Debug + Send + Serialize + Sync {
    fn len() -> usize;
    fn generate(rng: &mut StdRng) -> Self;
    fn cross(&mut self, other: &mut Self, i: usize);
    fn mutate(&mut self, rng: &mut StdRng, i: usize);
}

pub trait Evaluation {
    type Chromosome: Chromosome;

    fn evaluate(&self, population: &mut [Individual<Self::Chromosome>]);
}

#[derive(Clone, Debug, Serialize)]
pub struct Individual<T: Chromosome> {
    pub chromosome: T,
    pub fitness: f64,
}

impl<T: Chromosome> Individual<T> {
    fn generate(rng: &mut StdRng) -> Self {
        Self {
            chromosome: T::generate(rng),
            fitness: f64::MIN,
        }
    }

    fn fitness_desc(ind1: &Individual<T>, ind2: &Individual<T>) -> Ordering {
        ind2.fitness.partial_cmp(&ind1.fitness).unwrap()
    }
}

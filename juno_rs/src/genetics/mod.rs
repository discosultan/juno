pub mod algorithm;
pub mod crossover;
pub mod mutation;
pub mod reinsertion;
pub mod selection;

pub use algorithm::GeneticAlgorithm;

use juno_derive_rs::*;
use rand::prelude::*;
use serde::Serialize;
use std::{cmp::Ordering, fmt::Debug, time::Duration};

pub trait Chromosome: Clone + Send + Sync {
    type Context;

    fn len() -> usize;
    fn generate(rng: &mut StdRng, ctx: &Self::Context) -> Self;
    fn cross(&mut self, other: &mut Self, i: usize);
    fn mutate(&mut self, rng: &mut StdRng, i: usize, ctx: &Self::Context);
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
    fn generate(rng: &mut StdRng, ctx: &T::Context) -> Self {
        Self {
            chromosome: T::generate(rng, ctx),
            fitness: f64::MIN,
        }
    }

    fn fitness_desc(ind1: &Individual<T>, ind2: &Individual<T>) -> Ordering {
        ind2.fitness.partial_cmp(&ind1.fitness).unwrap()
    }
}

#[derive(Debug, Default)]
pub struct Timings {
    pub selection: Duration,
    pub crossover_mutation: Duration,
    pub evaluation: Duration,
    pub sorting: Duration,
}

pub struct Evolution<T: Chromosome> {
    pub generations: Vec<Generation<T>>,
    pub seed: u64,
}

pub struct Generation<T: Chromosome> {
    pub hall_of_fame: Vec<Individual<T>>,
    pub timings: Timings,
}

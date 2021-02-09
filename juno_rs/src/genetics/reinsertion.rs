use super::{Chromosome, Individual};
use rand::prelude::*;

pub trait Reinsertion {
    fn selection_rate(&self) -> f32;

    fn reinsert<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
        ctx: &T::Context,
    );
}

// Produce less offspring than parents and replace the worst parents.
pub struct EliteReinsertion {
    selection_rate: f32,
    generation_rate: f32,
}

impl EliteReinsertion {
    pub fn new(selection_rate: f32, generation_rate: f32) -> Self {
        assert!(0.0 < selection_rate && selection_rate < 1.0);
        assert!(0.0 <= generation_rate && generation_rate <= 1.0);
        Self {
            selection_rate,
            generation_rate,
        }
    }
}

impl Default for EliteReinsertion {
    fn default() -> Self {
        Self {
            selection_rate: 0.75,
            generation_rate: 0.0,
        }
    }
}

impl Reinsertion for EliteReinsertion {
    fn selection_rate(&self) -> f32 {
        self.selection_rate
    }

    fn reinsert<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
        ctx: &T::Context,
    ) {
        debug_assert!(offsprings.len() < population_size);

        // Both parents and offsprings are assumed to be ordered by fitness desc.
        let diff = population_size - offsprings.len();

        let num_gen = (diff as f32 * self.generation_rate) as usize;
        let num_parents = diff - num_gen;

        offsprings.extend_from_slice(&parents[..num_parents as usize]);
        for _ in 0..num_gen {
            offsprings.push(Individual::generate(rng, ctx));
        }
        offsprings.sort_by(Individual::fitness_desc);
    }
}

// Produce more offspring than needed for reinsertion and reinsert only the best offspring.
pub struct FitnessReinsertion {
    selection_rate: f32,
}

impl FitnessReinsertion {
    pub fn new(selection_rate: f32) -> Self {
        assert!(selection_rate > 1.0);
        Self { selection_rate }
    }
}

impl Default for FitnessReinsertion {
    fn default() -> Self {
        Self {
            selection_rate: 1.25,
        }
    }
}

impl Reinsertion for FitnessReinsertion {
    fn selection_rate(&self) -> f32 {
        self.selection_rate
    }

    fn reinsert<T: Chromosome>(
        &self,
        _rng: &mut StdRng,
        _parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
        _ctx: &T::Context,
    ) {
        debug_assert!(offsprings.len() > population_size);

        // Offsprings are assumed to be ordered by fitness desc.
        let diff = offsprings.len() - population_size;
        for _ in 0..diff {
            offsprings.pop();
        }
    }
}

// Produce as many offspring as parents and replace all parents by the offspring.
pub struct PureReinsertion {}

impl Reinsertion for PureReinsertion {
    fn selection_rate(&self) -> f32 {
        1.0
    }

    fn reinsert<T: Chromosome>(
        &self,
        _rng: &mut StdRng,
        _parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
        _ctx: &T::Context,
    ) {
        debug_assert_eq!(offsprings.len(), population_size)
    }
}

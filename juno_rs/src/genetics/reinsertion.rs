use super::{Chromosome, Individual};

pub trait Reinsertion {
    fn selection_rate(&self) -> f32;

    fn reinsert<T: Chromosome>(
        &self,
        parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
    );
}

// Produce less offspring than parents and replace the worst parents.
pub struct EliteReinsertion {
    selection_rate: f32,
}

impl EliteReinsertion {
    pub fn new(selection_rate: f32) -> Self {
        assert!(0.0 < selection_rate && selection_rate < 1.0);
        Self {
            selection_rate,
        }
    }
}

impl Default for EliteReinsertion {
    fn default() -> Self {
        Self {
            selection_rate: 0.75,
        }
    }
}

impl Reinsertion for EliteReinsertion {
    fn selection_rate(&self) -> f32 {
        self.selection_rate
    }

    fn reinsert<T: Chromosome>(
        &self,
        parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
    ) {
        assert!(offsprings.len() < population_size);

        // Both parents and offsprings are assumed to be ordered by fitness desc.
        let diff = population_size - offsprings.len();
        offsprings.extend_from_slice(&parents[..diff as usize]);
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
        Self {
            selection_rate,
        }
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
        _parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
    ) {
        assert!(offsprings.len() > population_size);

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
        _parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        population_size: usize,
    ) {
        assert_eq!(offsprings.len(), population_size)
    }
}

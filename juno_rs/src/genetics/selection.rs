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

impl EliteSelection {
    pub fn new(shuffle: bool) -> Self {
        Self {
            shuffle,
        }
    }
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

pub struct TournamentSelection {
    tournament_size_rate: f32,
    allow_winner_compete_next_tournament: bool,
}

impl TournamentSelection {
    pub fn new(tournament_size_rate: f32, allow_winner_compete_next_tournament: bool) -> Self {
        assert!(0.0 > tournament_size_rate && tournament_size_rate < 1.0);
        // TODO: Implement.
        assert!(allow_winner_compete_next_tournament);
        Self {
            tournament_size_rate: tournament_size_rate,
            allow_winner_compete_next_tournament,
        }
    }
}

impl Default for TournamentSelection {
    fn default() -> Self {
        Self {
            tournament_size_rate: 0.2,
            allow_winner_compete_next_tournament: true,
        }
    }
}

impl Selection for TournamentSelection {
    fn select<T: Chromosome>(
        &self,
        rng: &mut StdRng,
        parents: &[Individual<T>],
        offsprings: &mut Vec<Individual<T>>,
        rate: f32,
    ) {
        assert!(self.allow_winner_compete_next_tournament || rate <= 1.0);

        let tournament_size = (parents.len() as f32 * self.tournament_size_rate) as usize;

        let count = (parents.len() as f32 * rate) as usize;
        for _ in 0..count {
            let tournament = parents.choose_multiple(rng, tournament_size);
            let winner = tournament
                .max_by(|ind1, ind2| Individual::fitness_desc(ind1, ind2))
                .unwrap();
            offsprings.push(winner.clone());
        }
    }
}

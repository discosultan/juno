pub trait Selection {
    fn select(&self, fitnesses: &[f64], count: usize) -> Vec<usize>;
}

pub struct EliteSelection;

impl Selection for EliteSelection {
    fn select(&self, fitnesses: &[f64], count: usize) -> Vec<usize> {
        let mut fitness_copies: Vec<(usize, f64)> = fitnesses.iter().cloned().enumerate().collect();
        fitness_copies.sort_by(|(_, a), (_, b)| b.partial_cmp(a).unwrap());
        fitness_copies.iter().take(count).map(|(i, _)| i).cloned().collect()
    }
}

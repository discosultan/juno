use super::TakeProfit;
use crate::genetics::Chromosome;
use juno_derive_rs::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Copy, Debug, Deserialize, Serialize)]
pub struct NoopParams {}

pub struct Noop {}

impl Noop {
    pub fn new(_params: &NoopParams) -> Self {
        Self {}
    }
}

impl TakeProfit for Noop {}

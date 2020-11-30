use super::StopLoss;
use crate::genetics::Chromosome;
use juno_derive_rs::*;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Deserialize, Serialize)]
pub struct NoopParams {}

pub struct Noop {}

impl StopLoss for Noop {
    type Params = NoopParams;

    fn new(_params: &Self::Params) -> Self {
        Self {}
    }
}
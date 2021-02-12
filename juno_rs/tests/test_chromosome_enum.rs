use juno_derive_rs::*;
use juno_rs::genetics::Chromosome;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

pub trait Target {}

pub struct Foo {}
impl Foo {
    pub fn new(_: &FooParams) -> Self {
        Self {}
    }
}
impl Target for Foo {}

#[derive(Chromosome, Clone, Copy, Debug, Default, PartialEq)]
pub struct FooParams {
    a: u32,
    b: u32,
}

fn a(_rng: &mut StdRng) -> u32 {
    10
}
fn b(_rng: &mut StdRng) -> u32 {
    20
}

#[derive(ChromosomeEnum, Clone, Copy, Debug)]
pub enum TargetParams {
    Foo(FooParams),
}

#[test]
fn test_derive_chromosome_enum_len() {
    // 2 from FooParams + 1 from discriminant.
    assert_eq!(TargetParams::len(), 3)
}

#[test]
fn test_derive_chromosome_enum_generate() {
    let mut rng = StdRng::seed_from_u64(1);

    let output = TargetParams::generate(&mut rng, &TargetParamsContext::None);

    match output {
        TargetParams::Foo(output) => {
            assert_eq!(output.a, 10);
            assert_eq!(output.b, 20);
        }
    }
}

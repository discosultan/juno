use juno_derive_rs::*;
use juno_rs::genetics::Chromosome;
use rand::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Chromosome, Clone, Debug, Default, PartialEq)]
struct Regular {
    a: u32,
    b: u32,
}

fn a(_rng: &mut StdRng) -> u32 {
    10
}
fn b(_rng: &mut StdRng) -> u32 {
    20
}

#[test]
fn test_derive_regular_len() {
    assert_eq!(Regular::len(), 2);
}

#[test]
fn test_derive_regular_generate() {
    let mut rng = StdRng::seed_from_u64(1);

    let x = Regular::generate(&mut rng, &Default::default());
    assert_eq!(x.a, 10);
    assert_eq!(x.b, 20);
}

#[test]
fn test_derive_regular_mutate() {
    let mut rng = StdRng::seed_from_u64(1);
    let mut x = Regular { a: 1, b: 2 };

    x.mutate(&mut rng, 0, &Default::default());
    assert_eq!(x.a, 10);
    assert_eq!(x.b, 2);

    x.mutate(&mut rng, 1, &Default::default());
    assert_eq!(x.a, 10);
    assert_eq!(x.b, 20);
}

#[test]
fn test_derive_regular_crossover() {
    let mut x1 = Regular { a: 1, b: 2 };
    let mut x2 = Regular { a: 3, b: 4 };

    x1.cross(&mut x2, 0);
    assert_eq!(x1.a, 3);
    assert_eq!(x2.a, 1);
    assert_eq!(x1.b, 2);
    assert_eq!(x2.b, 4);

    x1.cross(&mut x2, 1);
    assert_eq!(x1.a, 3);
    assert_eq!(x2.a, 1);
    assert_eq!(x1.b, 4);
    assert_eq!(x2.b, 2);
}

#[derive(Chromosome, Clone)]
struct Aggregate {
    #[chromosome]
    agg_a: Regular,
    #[chromosome]
    agg_b: Regular,
    c: u32,
    d: u32,
}

fn c(_rng: &mut StdRng) -> u32 {
    30
}
fn d(_rng: &mut StdRng) -> u32 {
    40
}

#[test]
fn test_derive_aggregate_len() {
    assert_eq!(Aggregate::len(), 6);
}

#[test]
fn test_derive_aggregate_generate() {
    let mut rng = StdRng::seed_from_u64(1);

    let x = Aggregate::generate(&mut rng, &Default::default());
    assert_eq!(x.agg_a.a, 10);
    assert_eq!(x.agg_a.b, 20);
    assert_eq!(x.agg_b.a, 10);
    assert_eq!(x.agg_b.b, 20);
    assert_eq!(x.c, 30);
    assert_eq!(x.d, 40);
}

#[test]
fn test_derive_aggregate_mutate() {
    let mut rng = StdRng::seed_from_u64(1);
    let mut x = Aggregate {
        agg_a: Regular { a: 1, b: 2 },
        agg_b: Regular { a: 3, b: 4 },
        c: 5,
        d: 6,
    };

    x.mutate(&mut rng, 1, &Default::default());
    assert_eq!(x.agg_a, Regular { a: 1, b: 20 });
    assert_eq!(x.agg_b, Regular { a: 3, b: 4 });
    assert_eq!(x.c, 5);
    assert_eq!(x.d, 6);

    x.mutate(&mut rng, 2, &Default::default());
    assert_eq!(x.agg_a, Regular { a: 1, b: 20 });
    assert_eq!(x.agg_b, Regular { a: 10, b: 4 });
    assert_eq!(x.c, 5);
    assert_eq!(x.d, 6);

    x.mutate(&mut rng, 4, &Default::default());
    assert_eq!(x.agg_a, Regular { a: 1, b: 20 });
    assert_eq!(x.agg_b, Regular { a: 10, b: 4 });
    assert_eq!(x.c, 30);
    assert_eq!(x.d, 6);
}

#[test]
fn test_derive_aggregate_crossover() {
    let mut x1 = Aggregate {
        agg_a: Regular { a: 1, b: 2 },
        agg_b: Regular { a: 3, b: 4 },
        c: 5,
        d: 6,
    };
    let mut x2 = Aggregate {
        agg_a: Regular { a: 7, b: 8 },
        agg_b: Regular { a: 9, b: 10 },
        c: 11,
        d: 12,
    };

    x1.cross(&mut x2, 1);
    assert_eq!(x1.agg_a, Regular { a: 1, b: 8 });
    assert_eq!(x1.agg_b, Regular { a: 3, b: 4 });
    assert_eq!(x1.c, 5);
    assert_eq!(x1.d, 6);
    assert_eq!(x2.agg_a, Regular { a: 7, b: 2 });
    assert_eq!(x2.agg_b, Regular { a: 9, b: 10 });
    assert_eq!(x2.c, 11);
    assert_eq!(x2.d, 12);

    x1.cross(&mut x2, 2);
    assert_eq!(x1.agg_a, Regular { a: 1, b: 8 });
    assert_eq!(x1.agg_b, Regular { a: 9, b: 4 });
    assert_eq!(x1.c, 5);
    assert_eq!(x1.d, 6);
    assert_eq!(x2.agg_a, Regular { a: 7, b: 2 });
    assert_eq!(x2.agg_b, Regular { a: 3, b: 10 });
    assert_eq!(x2.c, 11);
    assert_eq!(x2.d, 12);

    x1.cross(&mut x2, 4);
    assert_eq!(x1.agg_a, Regular { a: 1, b: 8 });
    assert_eq!(x1.agg_b, Regular { a: 9, b: 4 });
    assert_eq!(x1.c, 11);
    assert_eq!(x1.d, 6);
    assert_eq!(x2.agg_a, Regular { a: 7, b: 2 });
    assert_eq!(x2.agg_b, Regular { a: 3, b: 10 });
    assert_eq!(x2.c, 5);
    assert_eq!(x2.d, 12);
}

#[test]
fn test_derive_context_generate() {
    let mut rng = StdRng::seed_from_u64(1);

    let x = Aggregate::generate(
        &mut rng,
        &AggregateContext {
            agg_a: Default::default(),
            agg_b: RegularContext {
                a: None,
                b: Some(200),
            },
            c: Default::default(),
            d: Some(400),
        },
    );
    assert_eq!(x.agg_a.a, 10);
    assert_eq!(x.agg_a.b, 20);
    assert_eq!(x.agg_b.a, 10);
    assert_eq!(x.agg_b.b, 200);
    assert_eq!(x.c, 30);
    assert_eq!(x.d, 400);
}

#[test]
fn test_derive_context_mutate() {
    let mut rng = StdRng::seed_from_u64(1);

    let mut x = Aggregate {
        agg_a: Regular { a: 1, b: 2 },
        agg_b: Regular { a: 3, b: 4 },
        c: 5,
        d: 6,
    };
    let ctx = AggregateContext {
        agg_a: Default::default(),
        agg_b: RegularContext {
            a: None,
            b: Some(200),
        },
        c: Default::default(),
        d: Some(400),
    };

    x.mutate(&mut rng, 1, &ctx);
    assert_eq!(x.agg_a.b, 20);

    x.mutate(&mut rng, 2, &ctx);
    assert_eq!(x.agg_b.a, 10);

    x.mutate(&mut rng, 3, &ctx);
    assert_eq!(x.agg_b.b, 200);

    x.mutate(&mut rng, 4, &ctx);
    assert_eq!(x.c, 30);

    x.mutate(&mut rng, 5, &ctx);
    assert_eq!(x.d, 400);
}

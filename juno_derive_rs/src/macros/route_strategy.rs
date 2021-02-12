use proc_macro::{TokenStream, TokenTree};
use quote::{format_ident, quote};
use syn::{parse_str, TypePath};

use crate::util;

const STRATEGIES: [&'static str; 7] = [
    "FourWeekRule",
    "TripleMA",
    "DoubleMAStoch",
    "DoubleMA",
    "SingleMA",
    "Sig<FourWeekRule>",
    "Sig<TripleMA>",
    // "SigOsc<TripleMA,Rsi>",
    // "SigOsc<DoubleMA,Rsi>",
];

pub fn route_strategy(input: TokenStream) -> TokenStream {
    let idents: Vec<_> = input
        .into_iter()
        .filter_map(|token| match token {
            TokenTree::Ident(ident) => Some(ident),
            _ => None,
        })
        .collect();

    let in_function = format_ident!("{}", idents[0].to_string());
    let in_strategy = format_ident!("{}", idents[1].to_string());
    let in_args = format_ident!("{}", idents[4].to_string());

    let identifiers = util::cartesian_product(vec![&STRATEGIES]);

    let strategy_quoted = identifiers.iter().map(|x| {
        format!(
            "{}",
            x[0].replace(">", "")
                .replace("<", "_")
                .replace(",", "_")
                .to_lowercase()
        )
    });
    let strategy = identifiers
        .iter()
        .map(|x| parse_str::<TypePath>(x[0]).unwrap().path);

    let result = quote! {
        match #in_strategy.as_ref() {
            #(
                #strategy_quoted => #in_function::<juno_rs::strategies::#strategy>(#in_args),
            )*
            _ => Err(anyhow::anyhow!("unsupported strategy: {}", #in_strategy)),
        }
    };
    result.into()
}

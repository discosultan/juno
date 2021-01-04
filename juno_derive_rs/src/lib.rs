use proc_macro::{TokenStream, TokenTree};
use quote::{format_ident, quote};
use syn::{parse_macro_input, parse_str, ItemStruct, TypePath};

#[proc_macro_derive(Chromosome)]
pub fn derive_chromosome(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    let field_count = input.fields.iter().count();
    let field_name = input.fields.iter().map(|field| &field.ident);

    let generate_field_name = field_name.clone();

    let cross_field_index = 0..field_count;
    let cross_field_name = field_name.clone();

    let mutate_field_index = 0..field_count;
    let mutate_field_name = field_name.clone();

    let output = quote! {
        impl #impl_generics Chromosome for #name #ty_generics #where_clause {
            fn len() -> usize {
                #field_count
            }

            fn generate(rng: &mut StdRng) -> Self {
                Self {
                    #(
                        #generate_field_name: #generate_field_name(rng),
                    )*
                }
            }

            fn cross(&mut self, other: &mut Self, i: usize) {
                match i {
                    #(
                        #cross_field_index => std::mem::swap(
                            &mut self.#cross_field_name,
                            &mut other.#cross_field_name,
                        ),
                    )*
                    _ => panic!("index out of bounds"),
                };
            }

            fn mutate(&mut self, rng: &mut StdRng, i: usize) {
                match i {
                    #(
                        #mutate_field_index => self.#mutate_field_name = #mutate_field_name(rng),
                    )*
                    _ => panic!("index out of bounds"),
                };
            }
        }
    };

    TokenStream::from(output)
}

#[proc_macro_derive(AggregateChromosome)]
pub fn derive_aggregate_chromosome(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    let field_name = input.fields.iter().map(|field| &field.ident);
    let field_type = input.fields.iter().map(|field| &field.ty);

    let len_field_type = field_type.clone();

    let generate_field_name = field_name.clone();
    let generate_field_type = field_type.clone();

    let cross_field_name = field_name.clone();
    let cross_field_type = field_type.clone();

    let mutate_field_name = field_name.clone();
    let mutate_field_type = field_type.clone();

    let output = quote! {
        impl #impl_generics Chromosome for #name #ty_generics #where_clause {
            fn len() -> usize {
                0 #(
                    + #len_field_type::len()
                )*
            }

            fn generate(rng: &mut StdRng) -> Self {
                Self {
                    #(
                        #generate_field_name: #generate_field_type::generate(rng),
                    )*
                }
            }

            fn cross(&mut self, other: &mut Self, mut i: usize) {
                #(
                    if i < #cross_field_type::len() {
                        self.#cross_field_name.cross(&mut other.#cross_field_name, i);
                        return;
                    }
                    i -= #cross_field_type::len();
                )*
                panic!("index out of bounds");
            }

            fn mutate(&mut self, rng: &mut StdRng, mut i: usize) {
                #(
                    if i < #mutate_field_type::len() {
                        self.#mutate_field_name.mutate(rng, i);
                        return;
                    }
                    i -= #mutate_field_type::len();
                )*
                panic!("index out of bounds");
            }
        }
    };

    TokenStream::from(output)
}

#[proc_macro_derive(Signal)]
pub fn derive_signal(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    let output = quote! {
        impl #impl_generics Signal for #name #ty_generics #where_clause {
            fn advice(&self) -> crate::Advice {
                self.advice
            }
        }
    };

    TokenStream::from(output)
}

const STRATEGIES: [&'static str; 1] = [
    "FourWeekRule",
    // "TripleMA",
    // "DoubleMAStoch",
    // "DoubleMA",
    // "SingleMA",
    // "Sig<FourWeekRule>",
    // "Sig<TripleMA>",
    // "SigOsc<TripleMA,Rsi>",
    // "SigOsc<DoubleMA,Rsi>",
];
const STOP_LOSSES: [&'static str; 4] = [
    "Noop",
    "Basic",
    "BasicPlusTrailing",
    "Trailing",
    // "Legacy",
];
const TAKE_PROFITS: [&'static str; 3] = [
    "Noop", "Basic", "Trending",
    // "Legacy",
];

#[proc_macro]
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
    let in_stop_loss = format_ident!("{}", idents[2].to_string());
    let in_take_profit = format_ident!("{}", idents[3].to_string());
    let in_args = format_ident!("{}", idents[4].to_string());

    let identifiers = cartesian_product(vec![&STRATEGIES, &STOP_LOSSES, &TAKE_PROFITS]);

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
    let stop_loss_quoted = identifiers.iter().map(|x| x[1].to_lowercase());
    let stop_loss = identifiers.iter().map(|x| format_ident!("{}", x[1]));
    let take_profit_quoted = identifiers.iter().map(|x| x[2].to_lowercase());
    let take_profit = identifiers.iter().map(|x| format_ident!("{}", x[2]));

    let result = quote! {
        match (#in_strategy.as_ref(), #in_stop_loss.as_ref(), #in_take_profit.as_ref()) {
            #(
                (#strategy_quoted, #stop_loss_quoted, #take_profit_quoted) => #in_function::<juno_rs::strategies::#strategy, juno_rs::stop_loss::#stop_loss, juno_rs::take_profit::#take_profit>(#in_args),
            )*
            _ => panic!("unsupported combination: {}, {}, {}", #in_strategy, #in_stop_loss, #in_take_profit),
        }
    };
    result.into()
}

// Ref: https://rosettacode.org/wiki/Cartesian_product_of_two_or_more_lists#Rust
fn cartesian_product(lists: Vec<&[&'static str]>) -> Vec<Vec<&'static str>> {
    let mut res: Vec<Vec<&'static str>> = vec![];

    let mut list_iter = lists.iter();
    if let Some(first_list) = list_iter.next() {
        for i in *first_list {
            res.push(vec![*i]);
        }
    }
    for l in list_iter {
        let mut tmp = vec![];
        for r in res {
            for &el in *l {
                let mut tmp_el = r.clone();
                tmp_el.push(el);
                tmp.push(tmp_el);
            }
        }
        res = tmp;
    }
    res
}

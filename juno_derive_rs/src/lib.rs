use proc_macro::{TokenStream, TokenTree};
use quote::{format_ident, quote};
use std::borrow::Cow;
use syn::{
    parse_macro_input, parse_quote, parse_str, Attribute, Field, GenericParam, Ident, ItemStruct,
    Lit, Meta, NestedMeta, Type, TypePath,
};

fn is_chromosome(field: &Field) -> bool {
    field
        .attrs
        .iter()
        .any(|attr| attr.path.is_ident("chromosome"))
}

// Limited such that child chromosomes need to come before any other field.
#[proc_macro_derive(Chromosome, attributes(chromosome))]
pub fn derive_chromosome(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    // Validate chromosome fields come before regular fields.
    let mut can_have_chromosome = true;
    for field in input.fields.iter() {
        if !is_chromosome(field) {
            can_have_chromosome = false;
        } else if !can_have_chromosome {
            panic!("Chromosome fields must come before regular fields!");
        }
    }

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    // Fields.
    // `cfield` - field marked as chromosome.
    // `rfield` - regular field.

    let cfield = input.fields.iter().filter(|field| is_chromosome(field));
    let cfield_name = cfield.clone().map(|field| &field.ident);
    let cfield_type = cfield.clone().map(|field| &field.ty);

    let rfield = input.fields.iter().filter(|field| !is_chromosome(field));
    let rfield_name = rfield.clone().map(|field| &field.ident);
    let rfield_type = rfield.clone().map(|field| &field.ty);

    let len_cfield_type = cfield_type.clone();
    let len_rfield_count = rfield_type.clone().count();

    let generate_cfield_name = cfield_name.clone();
    let generate_cfield_type = cfield_type.clone();
    let generate_rfield_name = rfield_name.clone();

    let cross_cfield_name = cfield_name.clone();
    let cross_cfield_type = cfield_type.clone();
    let cross_rfield_index = 0..len_rfield_count;
    let cross_rfield_name = rfield_name.clone();

    let mutate_cfield_name = cfield_name.clone();
    let mutate_cfield_type = cfield_type.clone();
    let mutate_rfield_index = 0..len_rfield_count;
    let mutate_rfield_name = rfield_name.clone();

    // Context.
    let generic_ty_idents = input
        .generics
        .params
        .iter()
        .filter_map(|generic| match generic {
            GenericParam::Type(type_) => Some(&type_.ident),
            _ => None,
        })
        .collect::<Vec<&Ident>>();
    let ctx_attrs = &input.attrs;
    let ctx_vis = &input.vis;
    let ctx_name = format_ident!("{}Context", name);
    let ctx_field = input.fields.iter();
    let ctx_field_vis = ctx_field.clone().map(|field| &field.vis);
    let ctx_field_name = ctx_field.clone().map(|field| &field.ident);
    let ctx_field_type = ctx_field.clone().map(|field| {
        let field_ty = &field.ty;
        if is_chromosome(field) {
            if let Type::Path(type_path) = field_ty {
                if let Some(type_ident) = type_path.path.get_ident() {
                    // Is generic type.
                    if generic_ty_idents.iter().any(|&ident| ident == type_ident) {
                        return quote! { #field_ty };
                    } else {
                        let type_ident = format_ident!("{}Context", type_ident);
                        return quote! { #type_ident };
                    }
                }
            }
            panic!("Not implemented");
        } else {
            quote! { Option<#field_ty> }
        }
    });
    let ctx_generic_ty = if generic_ty_idents.len() == 0 {
        quote! {}
    } else {
        quote! { <#(#generic_ty_idents),*> }
    };
    let ctx_generic_ty_ctx = if generic_ty_idents.len() == 0 {
        quote! {}
    } else {
        quote! { <#(#generic_ty_idents::Context),*> }
    };
    let ctx_field_attrs = ctx_field.clone().map(|field| {
        let mut is_serde_default = false;

        let mut field_attrs = field
            .attrs
            .iter()
            .filter(|attr| !attr.path.is_ident("chromosome"))
            .map(|attr| {
                if attr.path.is_ident("serde") {
                    let meta = attr.parse_meta().unwrap();
                    if let Meta::List(meta) = meta {
                        if let NestedMeta::Meta(meta) = &meta.nested[0] {
                            if let Meta::NameValue(meta) = meta {
                                if meta.path.is_ident("serialize_with")
                                    || meta.path.is_ident("deserialize_with")
                                {
                                    if let Lit::Str(value) = &meta.lit {
                                        let meta_path = &meta.path;
                                        let meta_lit = format!("{}_option", value.value());
                                        return Cow::Owned(Attribute {
                                            bracket_token: attr.bracket_token,
                                            pound_token: attr.pound_token,
                                            style: attr.style,
                                            path: attr.path.clone(),
                                            tokens: quote! { (#meta_path = #meta_lit) },
                                        });
                                    }
                                }
                            } else if let Meta::Path(path) = meta {
                                if path.is_ident("default") {
                                    is_serde_default = true;
                                }
                            }
                        }
                    }
                }
                Cow::Borrowed(attr)
            })
            .collect::<Vec<Cow<Attribute>>>();

        if !is_serde_default {
            // Add `#[serde(default)]`.
            field_attrs.push(Cow::Owned(parse_quote! { #[serde(default)] }));
        }

        field_attrs
    });

    let output = quote! {
        #(#ctx_attrs)*
        #[derive(Default, Deserialize, Serialize)]
        #ctx_vis struct #ctx_name #ctx_generic_ty {
            #(
                #(#ctx_field_attrs)*
                #ctx_field_vis #ctx_field_name: #ctx_field_type,
            )*
        }

        impl #impl_generics Chromosome for #name #ty_generics #where_clause {
            type Context = #ctx_name #ctx_generic_ty_ctx;

            fn len() -> usize {
                #(
                    #len_cfield_type::len() +
                )* #len_rfield_count
            }

            fn generate(rng: &mut StdRng, ctx: &Self::Context) -> Self {
                Self {
                    #(
                        #generate_cfield_name: #generate_cfield_type::generate(
                            rng,
                            &ctx.#generate_cfield_name,
                        ),
                    )*
                    #(
                        #generate_rfield_name: ctx.#generate_rfield_name
                            .unwrap_or_else(|| #generate_rfield_name(rng)),
                    )*
                }
            }

            fn cross(&mut self, other: &mut Self, mut i: usize) {
                #(
                    if i < #cross_cfield_type::len() {
                        self.#cross_cfield_name.cross(&mut other.#cross_cfield_name, i);
                        return;
                    }
                    i -= #cross_cfield_type::len();
                )*
                match i {
                    #(
                        #cross_rfield_index => std::mem::swap(
                            &mut self.#cross_rfield_name,
                            &mut other.#cross_rfield_name,
                        ),
                    )*
                    _ => panic!("index out of bounds"),
                };
            }

            fn mutate(&mut self, rng: &mut StdRng, mut i: usize, ctx: &Self::Context) {
                #(
                    if i < #mutate_cfield_type::len() {
                        self.#mutate_cfield_name.mutate(rng, i, &ctx.#mutate_cfield_name);
                        return;
                    }
                    i -= #mutate_cfield_type::len();
                )*
                match i {
                    #(
                        #mutate_rfield_index => self.#mutate_rfield_name =
                            ctx.#mutate_rfield_name.unwrap_or_else(|| #mutate_rfield_name(rng)),
                    )*
                    _ => panic!("index out of bounds"),
                };
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

const STRATEGIES: [&'static str; 2] = [
    "FourWeekRule",
    // "TripleMA",
    // "DoubleMAStoch",
    // "DoubleMA",
    // "SingleMA",
    "Sig<FourWeekRule>",
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
            _ => Err(anyhow::anyhow!("unsupported combination: {}, {}, {}", #in_strategy, #in_stop_loss, #in_take_profit)),
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

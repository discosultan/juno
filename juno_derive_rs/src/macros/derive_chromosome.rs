use proc_macro::TokenStream;
use quote::{format_ident, quote};
use std::borrow::Cow;
use syn::{
    parse_macro_input, parse_quote, Attribute, GenericParam, ItemStruct, Lit, Meta, NestedMeta,
    Type,
};

use crate::util;

// Limited such that child chromosomes need to come before any other field.
pub fn derive_chromosome(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    // Validate chromosome fields come before regular fields.
    let mut can_have_chromosome = true;
    for field in input.fields.iter() {
        if !util::is_chromosome(field) {
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

    let cfield = input
        .fields
        .iter()
        .filter(|field| util::is_chromosome(field));
    let cfield_name = cfield.clone().map(|field| &field.ident);
    let cfield_type = cfield.clone().map(|field| &field.ty);

    let rfield = input
        .fields
        .iter()
        .filter(|field| !util::is_chromosome(field));
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
        .collect::<Vec<_>>();
    let ctx_attrs = &input.attrs;
    let ctx_vis = &input.vis;
    let ctx_name = format_ident!("{}Context", name);
    let ctx_field = input.fields.iter();
    let ctx_field_vis = ctx_field.clone().map(|field| &field.vis);
    let ctx_field_name = ctx_field.clone().map(|field| &field.ident);
    let ctx_field_type = ctx_field.clone().map(|field| {
        let field_ty = &field.ty;
        if util::is_chromosome(field) {
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
                            }
                        }
                    }
                }
                Cow::Borrowed(attr)
            })
            .collect::<Vec<_>>();

        if !util::is_serde_default(field) {
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

            fn generate(rng: &mut rand::prelude::StdRng, ctx: &Self::Context) -> Self {
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

            fn mutate(&mut self, rng: &mut rand::prelude::StdRng, mut i: usize, ctx: &Self::Context) {
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
